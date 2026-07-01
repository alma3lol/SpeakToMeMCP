from __future__ import annotations

import threading
import time

import pytest
from typing import cast

from speaktome_mcp.contracts import ToolContractError
from speaktome_mcp.transcription import AudioBuffer
from speaktome_mcp.transcription import TranscriptionError
from tests.fakes import (
    FakeAudioCapture,
    FakeCompletedTranscript,
    FakeRecordingSession,
    FakeRollingSessionFactory,
    FakeRollingTranscriptionSession,
    FakeTranscriptionService,
    build_manager,
    make_captured_audio,
)


def test_start_listening_starts_rolling_mode_immediately() -> None:
    rolling_session = FakeRollingTranscriptionSession(device_id=7, sample_rate=22_050)
    rolling_session_factory = FakeRollingSessionFactory(rolling_session=rolling_session)
    manager = build_manager(rolling_session_factory=rolling_session_factory)

    result = manager.start_listening(duration_seconds=12, device_id=7, sample_rate=44_100)

    assert result == {
        "ok": True,
        "tool": "start_listening",
        "data": {
            "session_id": "session-123",
            "device_id": 7,
            "sample_rate": 22050,
            "state": "recording",
            "mode": "rolling",
            "duration_seconds": 12,
        },
    }
    assert rolling_session_factory.calls == [(12, 7, 44_100)]
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
    rolling_session_factory = FakeRollingSessionFactory(
        rolling_session=FakeRollingTranscriptionSession(device_id=11, sample_rate=16_000)
    )
    manager = build_manager(rolling_session_factory=rolling_session_factory)

    result = manager.start_listening(duration_seconds=9, device_id=None, sample_rate=None)

    assert result == {
        "ok": True,
        "tool": "start_listening",
        "data": {
            "session_id": "session-123",
            "device_id": 11,
            "sample_rate": 16000,
            "state": "recording",
            "mode": "rolling",
            "duration_seconds": 9,
        },
    }
    assert rolling_session_factory.calls == [(9, None, None)]


def test_start_listening_failure_cleans_up_state_and_session_data() -> None:
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            start_error=RuntimeError("microphone unavailable")
        )
    )

    with pytest.raises(RuntimeError, match="microphone unavailable"):
        manager.start_listening(duration_seconds=12)

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


def test_poll_failure_cleans_up_state_and_session_data() -> None:
    rolling_session = FakeRollingTranscriptionSession(
        stop_error=RuntimeError("stream stop failed")
    )
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(rolling_session=rolling_session)
    )
    manager.start_listening(duration_seconds=12)

    with pytest.raises(RuntimeError, match="stream stop failed"):
        manager.poll_transcription("session-123")

    assert rolling_session.stop_calls == 1
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


def test_poll_with_mismatched_session_rejects_before_stopping_worker() -> None:
    rolling_session = FakeRollingTranscriptionSession()
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(rolling_session=rolling_session)
    )
    manager.start_listening(duration_seconds=12)

    with pytest.raises(ToolContractError) as exc_info:
        manager.poll_transcription("session-456")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "poll_transcription",
        "error": {
            "code": "session_mismatch",
            "message": "Cannot poll transcription for a different session.",
            "details": {
                "active_session_id": "session-123",
                "requested_session_id": "session-456",
            },
        },
    }
    assert rolling_session.stop_calls == 0
    assert manager.has_active_session is True
    status_data = cast(dict[str, object], manager.get_server_status()["data"])
    assert status_data["state"] == "recording"


def test_transcription_failure_stops_and_clears_the_session() -> None:
    rolling_session = FakeRollingTranscriptionSession(
        stop_error=TranscriptionError("backend failed")
    )
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(rolling_session=rolling_session)
    )
    manager.start_listening(duration_seconds=12)

    with pytest.raises(TranscriptionError, match="backend failed"):
        manager.poll_transcription("session-123")

    assert rolling_session.stop_calls == 1
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


def test_poll_transcription_with_no_active_session_returns_contract_error() -> None:
    manager = build_manager()

    with pytest.raises(ToolContractError) as exc_info:
        manager.poll_transcription("session-123")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "poll_transcription",
        "error": {
            "code": "no_active_session",
            "message": "Cannot poll transcription because no active session exists.",
            "details": {
                "current_state": "idle",
            },
        },
    }


def test_poll_transcription_returns_pending_when_no_window_completed() -> None:
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                duration_seconds=12,
                completed_transcript=None,
            )
        )
    )
    manager.start_listening(duration_seconds=12)

    result = manager.poll_transcription("session-123")

    assert result == {
        "ok": True,
        "tool": "poll_transcription",
        "data": {
            "session_id": "session-123",
            "status": "pending",
            "transcript": "",
            "state": "idle",
            "duration_seconds": 12,
            "completed_windows": 0,
            "transcript_updated_at": None,
        },
    }
    assert manager.has_active_session is False
    assert manager.has_buffered_audio is False
    status_data = cast(dict[str, object], manager.get_server_status()["data"])
    assert status_data["state"] == "idle"


def test_poll_transcription_returns_latest_completed_window_only() -> None:
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                duration_seconds=12,
                completed_transcript=FakeCompletedTranscript(
                    transcript="second completed window",
                    completed_windows=2,
                    transcript_updated_at="2026-07-01T12:00:00Z",
                ),
            )
        )
    )
    manager.start_listening(duration_seconds=12)

    result = manager.poll_transcription("session-123")

    assert result == {
        "ok": True,
        "tool": "poll_transcription",
        "data": {
            "session_id": "session-123",
            "status": "ready",
            "transcript": "second completed window",
            "state": "idle",
            "duration_seconds": 12,
            "completed_windows": 2,
            "transcript_updated_at": "2026-07-01T12:00:00Z",
        },
    }


def test_poll_transcription_stops_and_discards_in_progress_window() -> None:
    rolling_session = FakeRollingTranscriptionSession(
        duration_seconds=12,
        completed_transcript=FakeCompletedTranscript(
            transcript="last complete window",
            completed_windows=1,
            transcript_updated_at="2026-07-01T12:00:00Z",
        ),
        in_progress_transcript="partial second window",
    )
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(rolling_session=rolling_session)
    )
    manager.start_listening(duration_seconds=12)

    result = manager.poll_transcription("session-123")

    result_data = cast(dict[str, object], result["data"])
    assert result_data["transcript"] == "last complete window"
    assert result_data["completed_windows"] == 1
    assert rolling_session.discarded_in_progress is True
    assert rolling_session.stop_calls == 1


def test_poll_transcription_during_in_flight_transcription_returns_immediately() -> None:
    transcription_started = threading.Event()
    release_transcription = threading.Event()

    class SlowBlockingTranscriptionService:
        def __init__(self) -> None:
            self.calls: list[AudioBuffer] = []

        def transcribe(self, audio: AudioBuffer) -> str:
            self.calls.append(audio)
            transcription_started.set()
            release_transcription.wait(timeout=1.0)
            return "tx-1"

    manager = build_manager(
        audio_capture=FakeAudioCapture(
            recording_session=FakeRecordingSession(
                captured_audio=make_captured_audio(
                    pcm_frames=b"\x01\x00\x02\x00",
                    sample_rate=16_000,
                )
            )
        ),
        transcription_service=cast(
            FakeTranscriptionService,
            cast(object, SlowBlockingTranscriptionService()),
        ),
        rolling_session_factory=None,
    )
    manager.start_listening(duration_seconds=cast(int, 0.01))

    assert transcription_started.wait(timeout=0.5) is True

    started_at = time.perf_counter()
    result = manager.poll_transcription("session-123")
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.05
    assert result == {
        "ok": True,
        "tool": "poll_transcription",
        "data": {
            "session_id": "session-123",
            "status": "pending",
            "transcript": "",
            "state": "idle",
            "duration_seconds": 0.01,
            "completed_windows": 0,
            "transcript_updated_at": None,
        },
    }

    release_transcription.set()
    time.sleep(0.02)
    assert manager.get_server_status()["data"] == {
        "state": "idle",
        "active_session_id": None,
    }


def test_repeated_poll_after_stop_returns_inactive_session_error() -> None:
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(
            rolling_session=FakeRollingTranscriptionSession(
                completed_transcript=FakeCompletedTranscript(
                    transcript="done",
                    completed_windows=1,
                    transcript_updated_at="2026-07-01T12:00:00Z",
                )
            )
        )
    )
    _ = manager.start_listening(duration_seconds=12)
    _ = manager.poll_transcription("session-123")

    with pytest.raises(ToolContractError) as exc_info:
        manager.poll_transcription("session-123")

    assert exc_info.value.payload["error"]["code"] == "no_active_session"


def test_stop_listening_alias_cleans_up_state_and_session_data() -> None:
    rolling_session = FakeRollingTranscriptionSession(
        stop_error=InterruptedError("recording interrupted")
    )
    manager = build_manager(
        rolling_session_factory=FakeRollingSessionFactory(rolling_session=rolling_session)
    )
    manager.start_listening(duration_seconds=12)

    with pytest.raises(InterruptedError, match="recording interrupted"):
        manager.stop_listening("session-123")

    assert rolling_session.stop_calls == 1
    assert manager.has_active_session is False
    assert manager.has_buffered_audio is False
    assert manager.get_server_status()["data"] == {
        "state": "idle",
        "active_session_id": None,
    }
