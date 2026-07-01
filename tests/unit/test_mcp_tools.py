from __future__ import annotations

import anyio

from speaktome_mcp.contracts import (
    ToolContractError,
    get_server_status_error,
    start_listening_error,
)
from speaktome_mcp.server import build_server
from speaktome_mcp.tools import SpeakToMeToolHandlers
from tests.fakes import FakeAudioCapture, FakeSessionManager, make_audio_input_device


def test_list_microphone_devices_returns_normalized_contract_payload() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(
            devices=[
                make_audio_input_device(
                    device_id=5,
                    name="Desk Mic",
                    max_input_channels=2,
                    default_sample_rate=48000,
                    is_default=True,
                )
            ]
        ),
        session_manager=FakeSessionManager(),
    )

    result = handlers.list_microphone_devices()

    assert result == {
        "ok": True,
        "tool": "list_microphone_devices",
        "data": {
            "devices": [
                {
                    "id": 5,
                    "name": "Desk Mic",
                    "max_input_channels": 2,
                    "default_sample_rate": 48000,
                    "is_default": True,
                }
            ]
        },
    }


def test_list_microphone_devices_maps_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(list_error=RuntimeError("permission denied")),
        session_manager=FakeSessionManager(),
    )

    result = handlers.list_microphone_devices()

    assert result == {
        "ok": False,
        "tool": "list_microphone_devices",
        "error": {
            "code": "runtime_failure",
            "message": "Failed to list microphone devices.",
            "details": {
                "exception_type": "RuntimeError",
                "reason": "permission denied",
            },
        },
    }


def test_start_listening_validates_arguments_before_delegating() -> None:
    session_manager = FakeSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
    )

    result = handlers.start_listening(device_id=-1, sample_rate=0)

    assert result == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "invalid_argument",
            "message": "device_id must be a non-negative integer or null.",
            "details": {
                "field": "device_id",
                "value": -1,
            },
        },
    }
    assert session_manager.start_calls == []


def test_start_listening_passes_tool_contract_errors_through() -> None:
    payload = start_listening_error(
        "invalid_state",
        "Cannot start listening unless the server is idle.",
        {"current_state": "recording", "expected_state": "idle"},
    )
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeSessionManager(start_error=ToolContractError(payload)),
    )

    result = handlers.start_listening(device_id=7, sample_rate=16000)

    assert result == payload


def test_start_listening_maps_no_microphone_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeSessionManager(start_error=RuntimeError("No input devices are available")),
    )

    result = handlers.start_listening()

    assert result == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "runtime_failure",
            "message": "Failed to start listening.",
            "details": {
                "exception_type": "RuntimeError",
                "reason": "No input devices are available",
            },
        },
    }


def test_stop_listening_validates_session_id() -> None:
    session_manager = FakeSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
    )

    result = handlers.stop_listening("   ")

    assert result == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "invalid_argument",
            "message": "session_id must be a non-empty string.",
            "details": {
                "field": "session_id",
                "value": "   ",
            },
        },
    }
    assert session_manager.stop_calls == []


def test_stop_listening_maps_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeSessionManager(stop_error=RuntimeError("stream stopped badly")),
    )

    result = handlers.stop_listening("session-123")

    assert result == {
        "ok": False,
        "tool": "stop_listening",
        "error": {
            "code": "runtime_failure",
            "message": "Failed to stop listening.",
            "details": {
                "exception_type": "RuntimeError",
                "reason": "stream stopped badly",
            },
        },
    }


def test_stop_listening_passes_no_active_session_error_through() -> None:
    payload = {
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
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeSessionManager(stop_error=ToolContractError(payload)),
    )

    result = handlers.stop_listening("session-123")

    assert result == payload


def test_get_server_status_is_forwarded_without_side_effects() -> None:
    session_manager = FakeSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
    )

    result = handlers.get_server_status()

    assert result == session_manager.status_result
    assert session_manager.status_calls == 1


def test_get_server_status_passes_tool_contract_errors_through() -> None:
    payload = get_server_status_error(
        "runtime_failure",
        "status backend unavailable",
        {"component": "state"},
    )
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeSessionManager(status_error=ToolContractError(payload)),
    )

    result = handlers.get_server_status()

    assert result == payload


def test_build_server_registers_exactly_four_tools() -> None:
    def handler_factory() -> SpeakToMeToolHandlers:
        return SpeakToMeToolHandlers(
            audio_capture=FakeAudioCapture(),
            session_manager=FakeSessionManager(),
        )

    server = build_server(handler_factory=handler_factory)

    async def collect_tool_names() -> list[str]:
        tools = await server.list_tools()
        return [tool.name for tool in tools]

    tool_names = anyio.run(collect_tool_names)

    assert tool_names == [
        "list_microphone_devices",
        "start_listening",
        "stop_listening",
        "get_server_status",
    ]
