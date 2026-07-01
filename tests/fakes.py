from __future__ import annotations

from dataclasses import dataclass

from speaktome_mcp.audio import AudioInputDevice, CapturedAudio
from speaktome_mcp.session import SessionManager
from speaktome_mcp.state import ServerStateMachine
from speaktome_mcp.transcription import AudioBuffer


def make_captured_audio(
    *,
    pcm_frames: bytes = b"\x01\x00\x02\x00",
    sample_rate: int = 16_000,
    channels: int = 1,
    sample_width_bytes: int = 2,
) -> CapturedAudio:
    return CapturedAudio(
        pcm_frames=pcm_frames,
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width_bytes,
    )


def make_audio_input_device(
    *,
    device_id: int = 1,
    name: str = "Fake Mic",
    max_input_channels: int = 1,
    default_sample_rate: int = 16_000,
    is_default: bool = True,
) -> AudioInputDevice:
    return AudioInputDevice(
        device_id=device_id,
        name=name,
        max_input_channels=max_input_channels,
        default_sample_rate=default_sample_rate,
        is_default=is_default,
    )


class FakeRecordingSession:
    def __init__(
        self,
        *,
        device_id: int = 1,
        sample_rate: int = 16_000,
        captured_audio: CapturedAudio | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.stop_calls = 0
        self._captured_audio = captured_audio or make_captured_audio(sample_rate=sample_rate)
        self._stop_error = stop_error

    def stop(self) -> CapturedAudio:
        self.stop_calls += 1
        if self._stop_error is not None:
            raise self._stop_error
        return self._captured_audio


class FakeAudioCapture:
    def __init__(
        self,
        *,
        devices: list[AudioInputDevice] | None = None,
        recording_session: FakeRecordingSession | None = None,
        list_error: Exception | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self.devices = devices or []
        self.recording_session = recording_session or FakeRecordingSession()
        self.list_error = list_error
        self.start_error = start_error
        self.list_calls = 0
        self.start_calls: list[tuple[int | None, int | None]] = []

    def list_input_devices(self) -> list[AudioInputDevice]:
        self.list_calls += 1
        if self.list_error is not None:
            raise self.list_error
        return self.devices

    def start_recording(
        self,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> FakeRecordingSession:
        self.start_calls.append((device_id, sample_rate))
        if self.start_error is not None:
            raise self.start_error
        return self.recording_session


class FakeTranscriptionService:
    def __init__(
        self,
        *,
        transcript: str = "hello from whisper",
        transcribe_error: Exception | None = None,
    ) -> None:
        self.transcript = transcript
        self.transcribe_error = transcribe_error
        self.calls: list[AudioBuffer] = []

    def transcribe(self, audio: AudioBuffer) -> str:
        self.calls.append(audio)
        if self.transcribe_error is not None:
            raise self.transcribe_error
        return self.transcript


class FakeSessionManager:
    def __init__(
        self,
        *,
        start_result: dict[str, object] | None = None,
        stop_result: dict[str, object] | None = None,
        status_result: dict[str, object] | None = None,
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
        status_error: Exception | None = None,
    ) -> None:
        self.start_result = start_result or {
            "ok": True,
            "tool": "start_listening",
            "data": {
                "session_id": "session-123",
                "device_id": 7,
                "sample_rate": 16000,
                "state": "recording",
            },
        }
        self.stop_result = stop_result or {
            "ok": True,
            "tool": "stop_listening",
            "data": {
                "session_id": "session-123",
                "transcript": "hello world",
                "state": "idle",
            },
        }
        self.status_result = status_result or {
            "ok": True,
            "tool": "get_server_status",
            "data": {
                "state": "idle",
                "active_session_id": None,
            },
        }
        self.start_error = start_error
        self.stop_error = stop_error
        self.status_error = status_error
        self.start_calls: list[tuple[int | None, int | None]] = []
        self.stop_calls: list[str] = []
        self.status_calls = 0

    def start_listening(
        self,
        *,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> dict[str, object]:
        self.start_calls.append((device_id, sample_rate))
        if self.start_error is not None:
            raise self.start_error
        return self.start_result

    def stop_listening(self, session_id: str) -> dict[str, object]:
        self.stop_calls.append(session_id)
        if self.stop_error is not None:
            raise self.stop_error
        return self.stop_result

    def get_server_status(self) -> dict[str, object]:
        self.status_calls += 1
        if self.status_error is not None:
            raise self.status_error
        return self.status_result


def build_manager(
    *,
    audio_capture: FakeAudioCapture | None = None,
    transcription_service: FakeTranscriptionService | None = None,
    session_id: str = "session-123",
) -> SessionManager:
    return SessionManager(
        state_machine=ServerStateMachine(),
        audio_capture=audio_capture or FakeAudioCapture(),
        transcription_service=transcription_service or FakeTranscriptionService(),
        session_id_factory=lambda: session_id,
    )
