from speaktome_mcp.contracts import (
    ERROR_INVALID_STATE,
    LifecycleState,
    get_server_status_error,
    get_server_status_success,
    list_microphone_devices_error,
    list_microphone_devices_success,
    poll_transcription_error,
    poll_transcription_success,
    speak_text_error,
    speak_text_success,
    start_listening_error,
    start_listening_success,
    stop_listening_error,
    stop_listening_success,
)


def test_list_microphone_devices_success_payload() -> None:
    payload = list_microphone_devices_success(
        [
            {
                "id": 3,
                "name": "USB Mic",
                "default_sample_rate": 48000,
                "max_input_channels": 1,
            }
        ]
    )

    assert payload == {
        "ok": True,
        "tool": "list_microphone_devices",
        "data": {
            "devices": [
                {
                    "id": 3,
                    "name": "USB Mic",
                    "default_sample_rate": 48000,
                    "max_input_channels": 1,
                }
            ]
        },
    }


def test_list_microphone_devices_error_payload() -> None:
    payload = list_microphone_devices_error(
        "runtime_failure",
        "Device query failed.",
        {"reason": "permission_denied"},
    )

    assert payload == {
        "ok": False,
        "tool": "list_microphone_devices",
        "error": {
            "code": "runtime_failure",
            "message": "Device query failed.",
            "details": {"reason": "permission_denied"},
        },
    }


def test_start_listening_success_payload() -> None:
    payload = start_listening_success(
        session_id="session-123",
        device_id=7,
        sample_rate=16000,
        duration_seconds=12,
    )

    assert payload == {
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


def test_start_listening_error_payload() -> None:
    payload = start_listening_error(
        ERROR_INVALID_STATE,
        "Cannot start listening unless the server is idle.",
        {"current_state": "recording", "expected_state": "idle"},
    )

    assert payload == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "invalid_state",
            "message": "Cannot start listening unless the server is idle.",
            "details": {
                "current_state": "recording",
                "expected_state": "idle",
            },
        },
    }


def test_poll_transcription_ready_success_payload() -> None:
    payload = poll_transcription_success(
        session_id="session-123",
        transcript="hello from whisper",
        duration_seconds=12,
        completed_windows=2,
        transcript_updated_at="2026-07-01T12:00:00Z",
    )

    assert payload == {
        "ok": True,
        "tool": "poll_transcription",
        "data": {
            "session_id": "session-123",
            "status": "ready",
            "transcript": "hello from whisper",
            "state": "idle",
            "duration_seconds": 12,
            "completed_windows": 2,
            "transcript_updated_at": "2026-07-01T12:00:00Z",
        },
    }


def test_poll_transcription_pending_success_payload() -> None:
    payload = poll_transcription_success(
        session_id="session-123",
        transcript="",
        duration_seconds=12,
        completed_windows=0,
        transcript_updated_at=None,
    )

    assert payload == {
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


def test_poll_transcription_error_payload() -> None:
    payload = poll_transcription_error(
        "no_active_session",
        "Cannot stop listening because no active session exists.",
        {"current_state": "idle"},
    )

    assert payload == {
        "ok": False,
        "tool": "poll_transcription",
        "error": {
            "code": "no_active_session",
            "message": "Cannot stop listening because no active session exists.",
            "details": {"current_state": "idle"},
        },
    }


def test_stop_listening_success_payload_marks_deprecated_alias() -> None:
    payload = stop_listening_success(
        session_id="session-123",
        transcript="hello from whisper",
        duration_seconds=12,
        completed_windows=2,
        transcript_updated_at="2026-07-01T12:00:00Z",
    )

    assert payload == {
        "ok": True,
        "tool": "stop_listening",
        "data": {
            "session_id": "session-123",
            "status": "ready",
            "transcript": "hello from whisper",
            "state": "idle",
            "duration_seconds": 12,
            "completed_windows": 2,
            "transcript_updated_at": "2026-07-01T12:00:00Z",
            "deprecated": True,
            "replacement": "poll_transcription",
        },
    }


def test_stop_listening_error_payload() -> None:
    payload = stop_listening_error(
        "no_active_session",
        "Cannot stop listening because no active session exists.",
        {"current_state": "idle"},
    )

    assert payload == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "no_active_session",
            "message": "Cannot stop listening because no active session exists.",
            "details": {"current_state": "idle"},
        },
    }


def test_speak_text_success_payload() -> None:
    payload = speak_text_success(characters=11)

    assert payload == {
        "ok": True,
        "tool": "speak_text",
        "data": {
            "spoken": True,
            "backend": "espeak-ng",
            "characters": 11,
        },
    }


def test_speak_text_error_payload() -> None:
    payload = speak_text_error(
        "invalid_argument",
        "text must be a non-empty string with at most 1000 characters.",
        {"field": "text", "value": ""},
    )

    assert payload == {
        "ok": False,
        "tool": "speak_text",
        "error": {
            "code": "invalid_argument",
            "message": "text must be a non-empty string with at most 1000 characters.",
            "details": {"field": "text", "value": ""},
        },
    }


def test_get_server_status_success_payload() -> None:
    payload = get_server_status_success(
        LifecycleState.TRANSCRIBING,
        active_session_id="session-123",
    )

    assert payload == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "transcribing",
            "active_session_id": "session-123",
        },
    }


def test_get_server_status_error_payload() -> None:
    payload = get_server_status_error(
        "runtime_failure",
        "State backend unavailable.",
        {"component": "state_manager"},
    )

    assert payload == {
        "ok": False,
        "tool": "get_server_status",
        "error": {
            "code": "runtime_failure",
            "message": "State backend unavailable.",
            "details": {"component": "state_manager"},
        },
    }
