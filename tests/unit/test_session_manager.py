from __future__ import annotations

import pytest

from speaktome_mcp.contracts import ToolContractError
from speaktome_mcp.transcription import TranscriptionError
from tests.fakes import (
    FakeAudioCapture,
    FakeRecordingSession,
    FakeTranscriptionService,
    build_manager,
    make_captured_audio,
)


def test_start_listening_creates_active_session_and_starts_capture() -> None:
    audio_capture = FakeAudioCapture(
        recording_session=FakeRecordingSession(device_id=7, sample_rate=22_050)
    )
    manager = build_manager(audio_capture=audio_capture)

    result = manager.start_listening(device_id=7, sample_rate=44_100)

    assert result == {
        "ok": True,
        "tool": "start_listening",
        "data": {
            "session_id": "session-123",
            "device_id": 7,
            "sample_rate": 22050,
            "state": "recording",
        },
    }
    assert audio_capture.start_calls == [(7, 44_100)]
    assert manager.has_active_session is True
    assert manager.has_buffered_audio is False
    assert manager.get_server_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "recording",
            "active_session_id": "session-123",
        },
    }


def test_start_listening_with_omitted_device_returns_resolved_default_device_id() -> None:
    audio_capture = FakeAudioCapture(
        recording_session=FakeRecordingSession(device_id=11, sample_rate=16_000)
    )
    manager = build_manager(audio_capture=audio_capture)

    result = manager.start_listening(device_id=None, sample_rate=None)

    assert result == {
        "ok": True,
        "tool": "start_listening",
        "data": {
            "session_id": "session-123",
            "device_id": 11,
            "sample_rate": 16000,
            "state": "recording",
        },
    }
    assert audio_capture.start_calls == [(None, None)]


def test_start_listening_failure_cleans_up_state_and_session_data() -> None:
    manager = build_manager(
        audio_capture=FakeAudioCapture(start_error=RuntimeError("microphone unavailable"))
    )

    with pytest.raises(RuntimeError, match="microphone unavailable"):
        manager.start_listening()

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


def test_stop_failure_cleans_up_state_and_session_data() -> None:
    recording_session = FakeRecordingSession(stop_error=RuntimeError("stream stop failed"))
    manager = build_manager(audio_capture=FakeAudioCapture(recording_session=recording_session))
    manager.start_listening()

    with pytest.raises(RuntimeError, match="stream stop failed"):
        manager.stop_listening("session-123")

    assert recording_session.stop_calls == 1
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


def test_stop_with_mismatched_session_rejects_before_stopping_capture() -> None:
    recording_session = FakeRecordingSession()
    manager = build_manager(audio_capture=FakeAudioCapture(recording_session=recording_session))
    manager.start_listening()

    with pytest.raises(ToolContractError) as exc_info:
        manager.stop_listening("session-456")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "session_mismatch",
            "message": "Cannot stop listening for a different session.",
            "details": {
                "active_session_id": "session-123",
                "requested_session_id": "session-456",
            },
        },
    }
    assert recording_session.stop_calls == 0
    assert manager.has_active_session is True
    assert manager.get_server_status()["data"]["state"] == "recording"


def test_transcription_failure_cleans_up_state_and_session_data() -> None:
    transcription_service = FakeTranscriptionService(
        transcribe_error=TranscriptionError("backend failed")
    )
    manager = build_manager(transcription_service=transcription_service)
    manager.start_listening()

    with pytest.raises(TranscriptionError, match="backend failed"):
        manager.stop_listening("session-123")

    assert len(transcription_service.calls) == 1
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


def test_stop_listening_with_no_active_session_returns_contract_error() -> None:
    manager = build_manager()

    with pytest.raises(ToolContractError) as exc_info:
        manager.stop_listening("session-123")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "no_active_session",
            "message": "Cannot stop listening because no active session exists.",
            "details": {
                "current_state": "idle",
            },
        },
    }


def test_silence_only_input_returns_empty_transcript_and_cleans_up() -> None:
    manager = build_manager(
        audio_capture=FakeAudioCapture(
            recording_session=FakeRecordingSession(
                captured_audio=make_captured_audio(pcm_frames=b"\x00\x00" * 32)
            )
        ),
        transcription_service=FakeTranscriptionService(transcript=""),
    )
    manager.start_listening()

    result = manager.stop_listening("session-123")

    assert result["data"]["transcript"] == ""
    assert manager.has_active_session is False
    assert manager.has_buffered_audio is False
    assert manager.get_server_status()["data"]["state"] == "idle"


def test_interrupted_recording_stop_cleans_up_state_and_session_data() -> None:
    recording_session = FakeRecordingSession(stop_error=InterruptedError("recording interrupted"))
    manager = build_manager(audio_capture=FakeAudioCapture(recording_session=recording_session))
    manager.start_listening()

    with pytest.raises(InterruptedError, match="recording interrupted"):
        manager.stop_listening("session-123")

    assert recording_session.stop_calls == 1
    assert manager.has_active_session is False
    assert manager.has_buffered_audio is False
    assert manager.get_server_status()["data"] == {
        "state": "idle",
        "active_session_id": None,
    }
