from __future__ import annotations

from typing import cast

from tests.fakes import (
    FakeCompletedTranscript,
    FakeRollingSessionFactory,
    FakeRollingTranscriptionSession,
    build_manager,
)


def test_stop_listening_returns_same_core_payload_as_poll_plus_deprecation_metadata() -> None:
    completed_transcript = FakeCompletedTranscript(
        transcript="normalized transcript",
        completed_windows=2,
        transcript_updated_at="2026-07-01T12:00:00Z",
    )
    poll_manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                duration_seconds=12,
                completed_transcript=completed_transcript,
            )
        )
    )
    stop_manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                duration_seconds=12,
                completed_transcript=completed_transcript,
            )
        )
    )

    start_result = stop_manager.start_listening(duration_seconds=12, device_id=None, sample_rate=None)
    poll_manager.start_listening(duration_seconds=12, device_id=None, sample_rate=None)
    poll_result = poll_manager.poll_transcription("session-123")
    stop_result = stop_manager.stop_listening("session-123")

    start_data = cast(dict[str, object], start_result["data"])
    poll_data = cast(dict[str, object], poll_result["data"])

    assert start_data["session_id"] == "session-123"
    assert poll_data == {
        "session_id": "session-123",
        "status": "ready",
        "transcript": "normalized transcript",
        "state": "idle",
        "duration_seconds": 12,
        "completed_windows": 2,
        "transcript_updated_at": "2026-07-01T12:00:00Z",
    }
    assert stop_result == {
        "ok": True,
        "tool": "stop_listening",
        "data": {
            "session_id": "session-123",
            "status": "ready",
            "transcript": "normalized transcript",
            "state": "idle",
            "duration_seconds": 12,
            "completed_windows": 2,
            "transcript_updated_at": "2026-07-01T12:00:00Z",
            "deprecated": True,
            "replacement": "poll_transcription",
        },
    }
    assert stop_manager.has_active_session is False
    assert stop_manager.has_buffered_audio is False
    assert stop_manager.get_server_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "idle",
            "active_session_id": None,
        },
    }


def test_stop_listening_returns_pending_payload_when_no_window_completed() -> None:
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                duration_seconds=6,
                completed_transcript=None,
            )
        )
    )

    manager.start_listening(duration_seconds=6)
    result = manager.stop_listening("session-123")

    assert result == {
        "ok": True,
        "tool": "stop_listening",
        "data": {
            "session_id": "session-123",
            "status": "pending",
            "transcript": "",
            "state": "idle",
            "duration_seconds": 6,
            "completed_windows": 0,
            "transcript_updated_at": None,
            "deprecated": True,
            "replacement": "poll_transcription",
        },
    }
