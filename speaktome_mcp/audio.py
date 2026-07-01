"""Audio capture abstractions and a sounddevice-backed microphone adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class AudioCaptureError(RuntimeError):
    """Base error for microphone capture failures."""


class NoInputDeviceError(AudioCaptureError):
    """Raised when no usable microphone input device is available."""


class DeviceNotFoundError(AudioCaptureError):
    """Raised when a requested input device cannot be found."""


class AudioPermissionError(AudioCaptureError):
    """Raised when microphone access is denied by the host system."""


@dataclass(frozen=True, slots=True)
class AudioInputDevice:
    """Normalized microphone input device information."""

    device_id: int
    name: str
    max_input_channels: int
    default_sample_rate: int
    is_default: bool


@dataclass(frozen=True, slots=True)
class CapturedAudio:
    """Mono PCM audio buffered in memory for a single recording session."""

    pcm_frames: bytes
    sample_rate: int
    channels: int = 1
    sample_width_bytes: int = 2


@runtime_checkable
class AudioRecordingSession(Protocol):
    """Active audio recording that can be stopped safely."""

    @property
    def device_id(self) -> int:
        """Return the resolved input device id used for this session."""

    @property
    def sample_rate(self) -> int:
        """Return the session sample rate."""

    def stop(self) -> CapturedAudio:
        """Stop recording, release resources, and return buffered audio."""


@runtime_checkable
class AudioCapture(Protocol):
    """Abstraction for microphone discovery and capture."""

    def list_input_devices(self) -> list[AudioInputDevice]:
        """Return all microphone-capable input devices."""

    def start_recording(
        self,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> AudioRecordingSession:
        """Open a microphone input and begin buffering mono PCM frames."""


class SoundDeviceAudioCapture:
    """Linux-oriented sounddevice adapter for microphone capture."""

    def __init__(self, sounddevice_module: Any) -> None:
        self._sounddevice = sounddevice_module
        self._input_stream_factory = sounddevice_module.InputStream

    def list_input_devices(self) -> list[AudioInputDevice]:
        devices = self._query_input_devices()
        default_input_id = self._resolve_default_input_id(devices)
        return [
            AudioInputDevice(
                device_id=device["index"],
                name=str(device["name"]),
                max_input_channels=int(device["max_input_channels"]),
                default_sample_rate=_normalize_sample_rate(device["default_samplerate"]),
                is_default=device["index"] == default_input_id,
            )
            for device in devices
        ]

    def start_recording(
        self,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> AudioRecordingSession:
        devices = self.list_input_devices()
        if not devices:
            raise NoInputDeviceError("No input devices are available")

        selected_device = self._select_device(devices, device_id)
        resolved_sample_rate = sample_rate or selected_device.default_sample_rate
        session = _SoundDeviceRecordingSession(
            sounddevice_module=self._sounddevice,
            input_stream_factory=self._input_stream_factory,
            device=selected_device,
            sample_rate=resolved_sample_rate,
        )
        session.start()
        return session

    def _select_device(
        self,
        devices: list[AudioInputDevice],
        requested_device_id: int | None,
    ) -> AudioInputDevice:
        if requested_device_id is not None:
            for device in devices:
                if device.device_id == requested_device_id:
                    return device
            raise DeviceNotFoundError(
                f"Input device {requested_device_id} was not found"
            )

        for device in devices:
            if device.is_default:
                return device

        return devices[0]

    def _query_input_devices(self) -> list[dict[str, Any]]:
        try:
            devices = self._sounddevice.query_devices()
        except Exception as exc:  # pragma: no cover - exercised in tests via fakes
            raise _map_sounddevice_error(exc) from exc

        input_devices: list[dict[str, Any]] = []
        for index, raw_device in enumerate(devices):
            max_input_channels = int(raw_device.get("max_input_channels", 0))
            if max_input_channels < 1:
                continue

            device = dict(raw_device)
            device.setdefault("index", index)
            input_devices.append(device)

        return input_devices

    def _resolve_default_input_id(self, devices: list[dict[str, Any]]) -> int | None:
        if not devices:
            return None

        default_device = getattr(getattr(self._sounddevice, "default", None), "device", None)
        candidate: int | None = None
        if isinstance(default_device, (list, tuple)) and default_device:
            candidate = int(default_device[0])
        elif isinstance(default_device, int):
            candidate = default_device

        valid_ids = {int(device["index"]) for device in devices}
        if candidate in valid_ids:
            return candidate

        return int(devices[0]["index"])


class _SoundDeviceRecordingSession:
    """Buffers frames from a sounddevice input stream until stopped."""

    def __init__(
        self,
        sounddevice_module: Any,
        input_stream_factory: Any,
        device: AudioInputDevice,
        sample_rate: int,
    ) -> None:
        self._sounddevice = sounddevice_module
        self._input_stream_factory = input_stream_factory
        self._device = device
        self._sample_rate = int(sample_rate)
        self._buffer = bytearray()
        self._stream: Any | None = None
        self._captured_audio: CapturedAudio | None = None
        self._stopped = False

    @property
    def device_id(self) -> int:
        return self._device.device_id

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(self) -> None:
        try:
            self._stream = self._input_stream_factory(
                device=self._device.device_id,
                channels=1,
                samplerate=self._sample_rate,
                dtype="int16",
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as exc:
            self._close_stream_quietly()
            raise _map_sounddevice_error(exc) from exc

    def stop(self) -> CapturedAudio:
        if self._captured_audio is not None:
            return self._captured_audio

        stop_error: AudioCaptureError | None = None
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception as exc:
                stop_error = _map_sounddevice_error(exc)
            finally:
                try:
                    self._stream.close()
                except Exception as exc:
                    if stop_error is None:
                        stop_error = _map_sounddevice_error(exc)

        self._stopped = True
        self._captured_audio = CapturedAudio(
            pcm_frames=bytes(self._buffer),
            sample_rate=self._sample_rate,
        )

        if stop_error is not None:
            raise stop_error

        return self._captured_audio

    def _close_stream_quietly(self) -> None:
        if self._stream is None:
            return

        try:
            self._stream.close()
        except Exception:
            pass

    def _on_audio(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info, status
        if self._stopped:
            return

        self._buffer.extend(_coerce_mono_pcm_bytes(indata))


def _normalize_sample_rate(value: Any) -> int:
    return int(round(float(value)))


def _map_sounddevice_error(exc: Exception) -> AudioCaptureError:
    message = str(exc)
    lowered = message.lower()
    if "permission denied" in lowered or "permission" in lowered:
        return AudioPermissionError(message)
    return AudioCaptureError(message)


def _coerce_mono_pcm_bytes(indata: Any) -> bytes:
    if hasattr(indata, "tobytes"):
        return bytes(indata.tobytes())

    if isinstance(indata, (bytes, bytearray, memoryview)):
        return bytes(indata)

    pcm = bytearray()
    for frame in indata:
        sample = frame[0] if isinstance(frame, (list, tuple)) else frame
        pcm.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


__all__ = [
    "AudioCapture",
    "AudioCaptureError",
    "AudioInputDevice",
    "AudioPermissionError",
    "AudioRecordingSession",
    "CapturedAudio",
    "DeviceNotFoundError",
    "NoInputDeviceError",
    "SoundDeviceAudioCapture",
]
