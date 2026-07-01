from speaktome_mcp.contracts import (
    ERROR_INVALID_STATE,
    LifecycleState,
    get_server_status_error,
    get_server_status_success,
    list_microphone_devices_error,
    list_microphone_devices_success,
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
    )

    assert payload == {
        "ok": True,
        "tool": "start_listening",
        "data": {
            "session_id": "session-123",
            "device_id": 7,
            "sample_rate": 16000,
            "state": "recording",
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


def test_stop_listening_success_payload() -> None:
    payload = stop_listening_success(
        session_id="session-123",
        transcript="hello from whisper",
    )

    assert payload == {
        "ok": True,
        "tool": "stop_listening",
        "data": {
            "session_id": "session-123",
            "transcript": "hello from whisper",
            "state": "idle",
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
