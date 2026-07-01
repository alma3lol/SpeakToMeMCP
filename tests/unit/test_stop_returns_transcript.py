from __future__ import annotations

from speaktome_mcp.transcription import AudioBuffer
from tests.fakes import (
    FakeAudioCapture,
    FakeRecordingSession,
    FakeTranscriptionService,
    build_manager,
    make_captured_audio,
)


def test_stop_listening_returns_transcript_once_and_resets_to_idle() -> None:
    recording_session = FakeRecordingSession(
        captured_audio=make_captured_audio(
            pcm_frames=b"\x01\x00\x02\x00\x03\x00",
            sample_rate=16_000,
        )
    )
    transcription_service = FakeTranscriptionService(transcript="normalized transcript")
    manager = build_manager(
        audio_capture=FakeAudioCapture(recording_session=recording_session),
        transcription_service=transcription_service,
    )

    start_result = manager.start_listening(device_id=None, sample_rate=None)
    stop_result = manager.stop_listening("session-123")

    assert start_result["data"]["session_id"] == "session-123"
    assert stop_result == {
        "ok": True,
        "tool": "stop_listening",
        "data": {
            "session_id": "session-123",
            "transcript": "normalized transcript",
            "state": "idle",
        },
    }
    assert recording_session.stop_calls == 1
    assert len(transcription_service.calls) == 1
    assert transcription_service.calls[0].data == b"\x01\x00\x02\x00\x03\x00"
    assert transcription_service.calls[0].sample_rate == 16_000
    assert transcription_service.calls[0].format == "pcm_s16le"
    assert manager.has_active_session is False
    assert manager.has_buffered_audio is False
    assert manager.get_server_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "idle",
            "active_session_id": None,
        },
    }


def test_stop_transitions_to_transcribing_before_transcription_runs() -> None:
    observed_states: list[str] = []

    class StateAssertingTranscriptionService:
        def __init__(self, manager: SessionManager) -> None:
            self._manager = manager

        def transcribe(self, audio: AudioBuffer) -> str:
            del audio
            observed_states.append(self._manager.get_server_status()["data"]["state"])
            return "transcribed"

    recording_session = FakeRecordingSession(captured_audio=make_captured_audio(pcm_frames=b"\x01\x00"))
    placeholder_transcriber = FakeTranscriptionService(transcript="unused")
    manager = build_manager(
        audio_capture=FakeAudioCapture(recording_session=recording_session),
        transcription_service=placeholder_transcriber,
    )
    manager._transcription_service = StateAssertingTranscriptionService(manager)

    manager.start_listening()
    result = manager.stop_listening("session-123")

    assert result["data"]["transcript"] == "transcribed"
    assert observed_states == ["transcribing"]
