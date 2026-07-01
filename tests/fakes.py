from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Any

from speaktome_mcp.audio import AudioInputDevice, CapturedAudio
from speaktome_mcp.session import SessionManager
from speaktome_mcp.state import ServerStateMachine
from speaktome_mcp.transcription import AudioBuffer


@dataclass(frozen=True)
class FakeCompletedTranscript:
    transcript: str
    completed_windows: int
    transcript_updated_at: str | None


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
                "mode": "rolling",
                "duration_seconds": 12,
            },
        }
        self.stop_result = stop_result or {
            "ok": True,
            "tool": "stop_listening",
            "data": {
                "session_id": "session-123",
                "status": "ready",
                "transcript": "hello world",
                "state": "idle",
                "duration_seconds": 12,
                "completed_windows": 1,
                "transcript_updated_at": "2026-07-01T12:00:00Z",
                "deprecated": True,
                "replacement": "poll_transcription",
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


class FakeSpeechService:
    def __init__(
        self,
        *,
        speak_error: Exception | None = None,
    ) -> None:
        self.speak_error = speak_error
        self.calls: list[str] = []

    def speak(self, text: str) -> None:
        self.calls.append(text)
        if self.speak_error is not None:
            raise self.speak_error


def build_manager(
    *,
    audio_capture: FakeAudioCapture | None = None,
    transcription_service: FakeTranscriptionService | None = None,
    rolling_session_factory: FakeRollingSessionFactory | None = None,
    session_id: str = "session-123",
) -> SessionManager:
    return SessionManager(
        state_machine=ServerStateMachine(),
        audio_capture=audio_capture or FakeAudioCapture(),
        transcription_service=transcription_service or FakeTranscriptionService(),
        rolling_session_factory=rolling_session_factory,
        session_id_factory=lambda: session_id,
    )


@dataclass
class FakeCompletedProcess:
    args: list[str]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeCommandRunner:
    def __init__(
        self,
        *,
        result: FakeCompletedProcess | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or FakeCompletedProcess(args=["espeak-ng", "--stdin"])
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(
            args=self.result.args,
            returncode=self.result.returncode,
            stdout=self.result.stdout,
            stderr=self.result.stderr,
        )


class FakeRollingTranscriptionSession:
    def __init__(
        self,
        *,
        device_id: int = 1,
        sample_rate: int = 16_000,
        duration_seconds: int = 12,
        completed_transcript: FakeCompletedTranscript | None = None,
        in_progress_transcript: str | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.duration_seconds = duration_seconds
        self.completed_transcript = completed_transcript
        self.in_progress_transcript = in_progress_transcript
        self.stop_error = stop_error
        self.stop_calls = 0
        self.discarded_in_progress = False

    def stop(self) -> FakeCompletedTranscript | None:
        self.stop_calls += 1
        if self.in_progress_transcript is not None:
            self.discarded_in_progress = True
        if self.stop_error is not None:
            raise self.stop_error
        return self.completed_transcript


class FakeRollingSessionFactory:
    def __init__(
        self,
        *,
        rolling_session: FakeRollingTranscriptionSession | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self.rolling_session = rolling_session or FakeRollingTranscriptionSession()
        self.start_error = start_error
        self.calls: list[tuple[int, int | None, int | None]] = []

    def __call__(
        self,
        *,
        duration_seconds: int,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> FakeRollingTranscriptionSession:
        self.calls.append((duration_seconds, device_id, sample_rate))
        if self.start_error is not None:
            raise self.start_error
        self.rolling_session.duration_seconds = duration_seconds
        return self.rolling_session
