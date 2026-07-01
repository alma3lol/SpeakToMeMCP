import pytest

from speaktome_mcp.contracts import ToolContractError
from speaktome_mcp.state import ServerStateMachine


def test_valid_lifecycle_transitions() -> None:
    machine = ServerStateMachine()

    assert machine.get_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "idle",
            "active_session_id": None,
        },
    }

    machine.start_listening("session-123")
    assert machine.get_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "recording",
            "active_session_id": "session-123",
        },
    }

    machine.stop_listening("session-123")
    assert machine.get_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "transcribing",
            "active_session_id": "session-123",
        },
    }

    machine.finish_transcription("session-123")
    assert machine.get_status() == {
        "ok": True,
        "tool": "get_server_status",
        "data": {
            "state": "idle",
            "active_session_id": None,
        },
    }


def test_invalid_double_start_while_recording_returns_structured_error() -> None:
    machine = ServerStateMachine()
    machine.start_listening("session-123")

    with pytest.raises(ToolContractError) as exc_info:
        machine.start_listening("session-456")

    assert exc_info.value.payload == {
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


def test_invalid_double_start_while_transcribing_returns_structured_error() -> None:
    machine = ServerStateMachine()
    machine.start_listening("session-123")
    machine.stop_listening("session-123")

    with pytest.raises(ToolContractError) as exc_info:
        machine.start_listening("session-456")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "invalid_state",
            "message": "Cannot start listening unless the server is idle.",
            "details": {
                "current_state": "transcribing",
                "expected_state": "idle",
            },
        },
    }


def test_invalid_stop_without_active_session_returns_structured_error() -> None:
    machine = ServerStateMachine()

    with pytest.raises(ToolContractError) as exc_info:
        machine.stop_listening("session-123")

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


def test_invalid_stop_with_session_mismatch_returns_structured_error() -> None:
    machine = ServerStateMachine()
    machine.start_listening("session-123")

    with pytest.raises(ToolContractError) as exc_info:
        machine.stop_listening("session-456")

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


def test_invalid_stop_while_transcribing_returns_structured_error() -> None:
    machine = ServerStateMachine()
    machine.start_listening("session-123")
    machine.stop_listening("session-123")

    with pytest.raises(ToolContractError) as exc_info:
        machine.stop_listening("session-123")

    assert exc_info.value.payload == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "invalid_state",
            "message": "Cannot stop listening unless the server is recording.",
            "details": {
                "current_state": "transcribing",
                "expected_state": "recording",
                "active_session_id": "session-123",
            },
        },
    }
