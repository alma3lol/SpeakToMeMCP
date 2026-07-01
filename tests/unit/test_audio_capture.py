from __future__ import annotations

from types import SimpleNamespace

import pytest

from speaktome_mcp.audio import (
    AudioCaptureError,
    AudioPermissionError,
    DeviceNotFoundError,
    NoInputDeviceError,
    SoundDeviceAudioCapture,
)


class FakePortAudioError(RuntimeError):
    pass


class FakeFrameBlock:
    def __init__(self, samples: list[int]) -> None:
        self._samples = samples

    def tobytes(self) -> bytes:
        pcm = bytearray()
        for sample in self._samples:
            pcm.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
        return bytes(pcm)


class FakeInputStream:
    def __init__(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback,
        emitted_blocks: list[FakeFrameBlock] | None = None,
        fail_on_start: Exception | None = None,
    ) -> None:
        self.device = device
        self.channels = channels
        self.samplerate = samplerate
        self.dtype = dtype
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False
        self._emitted_blocks = emitted_blocks or []
        self._fail_on_start = fail_on_start

    def start(self) -> None:
        if self._fail_on_start is not None:
            raise self._fail_on_start

        self.started = True
        for block in self._emitted_blocks:
            self.callback(block, len(block.tobytes()) // 2, None, None)

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeSoundDeviceModule:
    PortAudioError = FakePortAudioError

    def __init__(
        self,
        *,
        devices: list[dict[str, object]],
        default_device: object = (0, 0),
        emitted_blocks: list[FakeFrameBlock] | None = None,
        query_error: Exception | None = None,
        stream_start_error: Exception | None = None,
    ) -> None:
        self._devices = devices
        self.default = SimpleNamespace(device=default_device)
        self._emitted_blocks = emitted_blocks or []
        self._query_error = query_error
        self._stream_start_error = stream_start_error
        self.created_streams: list[FakeInputStream] = []
        self.InputStream = self._build_input_stream

    def query_devices(self) -> list[dict[str, object]]:
        if self._query_error is not None:
            raise self._query_error
        return self._devices

    def _build_input_stream(self, **kwargs):
        stream = FakeInputStream(
            **kwargs,
            emitted_blocks=list(self._emitted_blocks),
            fail_on_start=self._stream_start_error,
        )
        self.created_streams.append(stream)
        return stream


def test_start_recording_uses_default_device_sample_rate_and_buffers_frames() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "USB Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
        ],
        emitted_blocks=[FakeFrameBlock([100, -100]), FakeFrameBlock([200])],
    )

    audio_capture = SoundDeviceAudioCapture(sounddevice_module)
    session = audio_capture.start_recording()
    captured = session.stop()

    assert session.device_id == 0
    assert session.sample_rate == 16000
    assert captured.sample_rate == 16000
    assert captured.channels == 1
    assert captured.pcm_frames == (
        (100).to_bytes(2, byteorder="little", signed=True)
        + (-100).to_bytes(2, byteorder="little", signed=True)
        + (200).to_bytes(2, byteorder="little", signed=True)
    )

    stream = sounddevice_module.created_streams[0]
    assert stream.device == 0
    assert stream.channels == 1
    assert stream.samplerate == 16000
    assert stream.dtype == "int16"
    assert stream.started is True
    assert stream.stopped is True
    assert stream.closed is True


def test_start_recording_respects_selected_device_and_explicit_sample_rate() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "Built-in Mic",
                "max_input_channels": 1,
                "default_samplerate": 22050,
            },
            {
                "name": "USB Mic",
                "max_input_channels": 2,
                "default_samplerate": 48000,
            },
        ],
        default_device=(0, 0),
    )

    audio_capture = SoundDeviceAudioCapture(sounddevice_module)
    session = audio_capture.start_recording(device_id=1, sample_rate=44100)
    session.stop()

    assert session.device_id == 1
    stream = sounddevice_module.created_streams[0]
    assert stream.device == 1
    assert stream.samplerate == 44100


def test_stop_is_idempotent_and_returns_same_buffer() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "Desk Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
        ],
        emitted_blocks=[FakeFrameBlock([1, 2, 3])],
    )

    session = SoundDeviceAudioCapture(sounddevice_module).start_recording()

    first = session.stop()
    second = session.stop()

    assert first is second
    assert sounddevice_module.created_streams[0].closed is True


def test_start_recording_raises_no_device_error_when_no_inputs_exist() -> None:
    sounddevice_module = FakeSoundDeviceModule(devices=[])

    with pytest.raises(NoInputDeviceError, match="No input devices"):
        SoundDeviceAudioCapture(sounddevice_module).start_recording()


def test_start_recording_raises_device_not_found_for_unknown_input() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "Only Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
        ]
    )

    with pytest.raises(DeviceNotFoundError, match="Input device 99"):
        SoundDeviceAudioCapture(sounddevice_module).start_recording(device_id=99)


def test_list_input_devices_surfaces_permission_denied_errors() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[],
        query_error=FakePortAudioError("Error querying device: Permission denied"),
    )

    with pytest.raises(AudioPermissionError, match="Permission denied"):
        SoundDeviceAudioCapture(sounddevice_module).list_input_devices()


def test_start_recording_closes_stream_and_raises_permission_denied() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "USB Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
        ],
        stream_start_error=FakePortAudioError("Microphone open failed: Permission denied"),
    )

    with pytest.raises(AudioPermissionError, match="Permission denied"):
        SoundDeviceAudioCapture(sounddevice_module).start_recording()

    stream = sounddevice_module.created_streams[0]
    assert stream.closed is True


def test_start_recording_wraps_non_permission_failures() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "USB Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
        ],
        stream_start_error=RuntimeError("backend exploded"),
    )

    with pytest.raises(AudioCaptureError, match="backend exploded"):
        SoundDeviceAudioCapture(sounddevice_module).start_recording()
