from __future__ import annotations

import anyio
import pytest

from speaktome_mcp.contracts import (
    ToolContractError,
    get_server_status_error,
    poll_transcription_error,
    speak_text_error,
    start_listening_error,
)
from speaktome_mcp.server import build_default_tool_handlers, build_server
from speaktome_mcp.tools import SpeakToMeToolHandlers
from tests.fakes import FakeAudioCapture, FakeSessionManager, FakeSpeechService, make_audio_input_device


class FakeRollingSessionManager:
    def __init__(
        self,
        *,
        start_result: dict[str, object] | None = None,
        poll_result: dict[str, object] | None = None,
        stop_result: dict[str, object] | None = None,
        status_result: dict[str, object] | None = None,
        start_error: Exception | None = None,
        poll_error: Exception | None = None,
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
        self.poll_result = poll_result or {
            "ok": True,
            "tool": "poll_transcription",
            "data": {
                "session_id": "session-123",
                "status": "ready",
                "transcript": "hello world",
                "state": "idle",
                "duration_seconds": 12,
                "completed_windows": 1,
                "transcript_updated_at": "2026-07-01T12:00:00Z",
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
        self.poll_error = poll_error
        self.stop_error = stop_error
        self.status_error = status_error
        self.start_calls: list[tuple[int, int | None, int | None]] = []
        self.poll_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.status_calls = 0

    def start_listening(
        self,
        *,
        duration_seconds: int,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> dict[str, object]:
        self.start_calls.append((duration_seconds, device_id, sample_rate))
        if self.start_error is not None:
            raise self.start_error
        return self.start_result

    def poll_transcription(self, session_id: str) -> dict[str, object]:
        self.poll_calls.append(session_id)
        if self.poll_error is not None:
            raise self.poll_error
        return self.poll_result

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
        speech_service=FakeSpeechService(),
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
        speech_service=FakeSpeechService(),
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
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
    )

    result = handlers.start_listening(duration_seconds=0, device_id=-1, sample_rate=0)

    assert result == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "invalid_argument",
            "message": "duration_seconds must be an integer between 1 and 30.",
            "details": {
                "field": "duration_seconds",
                "value": 0,
            },
        },
    }
    assert session_manager.start_calls == []


def test_start_listening_rejects_missing_duration_seconds() -> None:
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
    )

    result = handlers.start_listening(duration_seconds=None)

    assert result == {
        "ok": False,
        "tool": "start_listening",
        "error": {
            "code": "invalid_argument",
            "message": "duration_seconds must be an integer between 1 and 30.",
            "details": {
                "field": "duration_seconds",
                "value": None,
            },
        },
    }
    assert session_manager.start_calls == []


def test_start_listening_rejects_out_of_range_or_non_int_duration_seconds() -> None:
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
    )

    too_large = handlers.start_listening(duration_seconds=31)
    wrong_type = handlers.start_listening(duration_seconds="10")

    assert too_large["ok"] is False
    assert too_large["tool"] == "start_listening"
    assert too_large["error"]["code"] == "invalid_argument"
    assert too_large["error"]["message"] == "duration_seconds must be an integer between 1 and 30."
    assert too_large["error"]["details"] == {"field": "duration_seconds", "value": 31}
    assert wrong_type["error"]["details"] == {"field": "duration_seconds", "value": "10"}
    assert session_manager.start_calls == []


def test_start_listening_passes_tool_contract_errors_through() -> None:
    payload = start_listening_error(
        "invalid_state",
        "Cannot start listening unless the server is idle.",
        {"current_state": "recording", "expected_state": "idle"},
    )
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(start_error=ToolContractError(payload)),
        speech_service=FakeSpeechService(),
    )

    result = handlers.start_listening(duration_seconds=12, device_id=7, sample_rate=16000)

    assert result == payload


def test_start_listening_maps_no_microphone_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(start_error=RuntimeError("No input devices are available")),
        speech_service=FakeSpeechService(),
    )

    result = handlers.start_listening(duration_seconds=12)

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


def test_start_listening_forwards_validated_duration_to_session_manager() -> None:
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
    )

    result = handlers.start_listening(duration_seconds=12, device_id=7, sample_rate=16000)

    assert result == session_manager.start_result
    assert session_manager.start_calls == [(12, 7, 16000)]


def test_stop_listening_validates_session_id() -> None:
    session_manager = FakeSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
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
        speech_service=FakeSpeechService(),
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
        speech_service=FakeSpeechService(),
    )

    result = handlers.stop_listening("session-123")

    assert result == payload


def test_poll_transcription_validates_session_id() -> None:
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
    )

    result = handlers.poll_transcription("   ")

    assert result == {
        "ok": False,
        "tool": "poll_transcription",
        "error": {
            "code": "invalid_argument",
            "message": "session_id must be a non-empty string.",
            "details": {
                "field": "session_id",
                "value": "   ",
            },
        },
    }
    assert session_manager.poll_calls == []


def test_poll_transcription_passes_tool_contract_errors_through() -> None:
    payload = poll_transcription_error(
        "no_active_session",
        "Cannot stop listening because no active session exists.",
        {"current_state": "idle"},
    )
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(poll_error=ToolContractError(payload)),
        speech_service=FakeSpeechService(),
    )

    result = handlers.poll_transcription("session-123")

    assert result == payload


def test_poll_transcription_maps_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(poll_error=RuntimeError("worker crashed")),
        speech_service=FakeSpeechService(),
    )

    result = handlers.poll_transcription("session-123")

    assert result == {
        "ok": False,
        "tool": "poll_transcription",
        "error": {
            "code": "runtime_failure",
            "message": "Failed to poll transcription.",
            "details": {
                "exception_type": "RuntimeError",
                "reason": "worker crashed",
            },
        },
    }


def test_speak_text_validates_text_before_delegating() -> None:
    speech_service = FakeSpeechService()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(),
        speech_service=speech_service,
    )

    empty_result = handlers.speak_text("   ")
    long_result = handlers.speak_text("x" * 1001)

    assert empty_result == {
        "ok": False,
        "tool": "speak_text",
        "error": {
            "code": "invalid_argument",
            "message": "text must be a non-empty string with at most 1000 characters.",
            "details": {
                "field": "text",
                "value": "   ",
            },
        },
    }
    assert long_result["error"] == {
        "code": "invalid_argument",
        "message": "text must be a non-empty string with at most 1000 characters.",
        "details": {
            "field": "text",
            "value": "x" * 1001,
        },
    }
    assert speech_service.calls == []


def test_speak_text_passes_tool_contract_errors_through() -> None:
    payload = speak_text_error(
        "runtime_failure",
        "Speech backend unavailable.",
        {"backend": "espeak-ng"},
    )
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(),
        speech_service=FakeSpeechService(speak_error=ToolContractError(payload)),
    )

    result = handlers.speak_text("hello world")

    assert result == payload


def test_speak_text_maps_runtime_failures() -> None:
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=FakeRollingSessionManager(),
        speech_service=FakeSpeechService(speak_error=RuntimeError("missing binary")),
    )

    result = handlers.speak_text("hello world")

    assert result == {
        "ok": False,
        "tool": "speak_text",
        "error": {
            "code": "runtime_failure",
            "message": "Failed to speak text.",
            "details": {
                "exception_type": "RuntimeError",
                "reason": "missing binary",
            },
        },
    }


def test_speak_text_uses_speech_service_and_returns_contract_success() -> None:
    speech_service = FakeSpeechService()
    session_manager = FakeRollingSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=speech_service,
    )

    result = handlers.speak_text("hello world")

    assert result == {
        "ok": True,
        "tool": "speak_text",
        "data": {
            "spoken": True,
            "backend": "espeak-ng",
            "characters": 11,
        },
    }
    assert speech_service.calls == ["hello world"]


def test_get_server_status_is_forwarded_without_side_effects() -> None:
    session_manager = FakeSessionManager()
    handlers = SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(),
        session_manager=session_manager,
        speech_service=FakeSpeechService(),
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
        speech_service=FakeSpeechService(),
    )

    result = handlers.get_server_status()

    assert result == payload


def test_build_server_registers_exactly_six_tools_in_primary_order() -> None:
    def handler_factory() -> SpeakToMeToolHandlers:
        return SpeakToMeToolHandlers(
            audio_capture=FakeAudioCapture(),
            session_manager=FakeRollingSessionManager(),
            speech_service=FakeSpeechService(),
        )

    server = build_server(handler_factory=handler_factory)

    async def collect_tool_names() -> list[str]:
        tools = await server.list_tools()
        return [tool.name for tool in tools]

    tool_names = anyio.run(collect_tool_names)

    assert tool_names == [
        "list_microphone_devices",
        "start_listening",
        "poll_transcription",
        "stop_listening",
        "speak_text",
        "get_server_status",
    ]


def test_build_default_tool_handlers_wires_audio_transcription_session_and_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sounddevice_module = object()
    fake_audio_capture = object()
    fake_transcription_service = object()
    fake_speech_service = object()
    captured_session_kwargs: dict[str, object] = {}

    class FakeSessionManagerForWiring:
        def __init__(self, **kwargs: object) -> None:
            captured_session_kwargs.update(kwargs)

    monkeypatch.setattr("speaktome_mcp.server.import_module", lambda name: fake_sounddevice_module if name == "sounddevice" else None)
    monkeypatch.setattr("speaktome_mcp.server.SoundDeviceAudioCapture", lambda module: fake_audio_capture if module is fake_sounddevice_module else None)
    monkeypatch.setattr("speaktome_mcp.server.load_transcription_service", lambda: fake_transcription_service)
    monkeypatch.setattr("speaktome_mcp.server.EspeakSpeechService", lambda: fake_speech_service)
    monkeypatch.setattr("speaktome_mcp.server.SessionManager", FakeSessionManagerForWiring)

    handlers = build_default_tool_handlers()

    assert handlers.audio_capture is fake_audio_capture
    assert handlers.speech_service is fake_speech_service
    assert isinstance(handlers.session_manager, FakeSessionManagerForWiring)
    assert captured_session_kwargs["audio_capture"] is fake_audio_capture
    assert captured_session_kwargs["transcription_service"] is fake_transcription_service


def test_build_server_is_lazy_by_default() -> None:
    calls = 0

    def handler_factory() -> SpeakToMeToolHandlers:
        nonlocal calls
        calls += 1
        return SpeakToMeToolHandlers(
            audio_capture=FakeAudioCapture(),
            session_manager=FakeRollingSessionManager(),
            speech_service=FakeSpeechService(),
        )

    server = build_server(handler_factory=handler_factory, eager=False)

    assert server.name == "speaktome-mcp"
    assert calls == 0
