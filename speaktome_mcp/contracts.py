"""Deterministic tool payload helpers for the SpeakToMe MCP server."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class LifecycleState(StrEnum):
    """Canonical lifecycle states for the server."""

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


TOOL_LIST_MICROPHONE_DEVICES = "list_microphone_devices"
TOOL_START_LISTENING = "start_listening"
TOOL_POLL_TRANSCRIPTION = "poll_transcription"
TOOL_STOP_LISTENING = "stop_listening"
TOOL_SPEAK_TEXT = "speak_text"
TOOL_GET_SERVER_STATUS = "get_server_status"


ERROR_INVALID_STATE = "invalid_state"
ERROR_INVALID_ARGUMENT = "invalid_argument"
ERROR_NO_ACTIVE_SESSION = "no_active_session"
ERROR_SESSION_MISMATCH = "session_mismatch"
ERROR_RUNTIME_FAILURE = "runtime_failure"


def build_tool_success(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic success payload for a tool call."""

    return {
        "ok": True,
        "tool": tool,
        "data": data,
    }


def build_tool_error(
    tool: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic structured error payload for a tool call."""

    return {
        "ok": False,
        "tool": tool,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


class ToolContractError(RuntimeError):
    """Raised when a tool request cannot be fulfilled under the contract."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        message = payload["error"]["message"]
        super().__init__(message)


def list_microphone_devices_success(devices: list[dict[str, Any]]) -> dict[str, Any]:
    return build_tool_success(
        TOOL_LIST_MICROPHONE_DEVICES,
        {
            "devices": devices,
        },
    )


def list_microphone_devices_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_LIST_MICROPHONE_DEVICES, code, message, details)


def start_listening_success(
    session_id: str,
    device_id: int | None,
    sample_rate: int,
    duration_seconds: int,
    state: LifecycleState = LifecycleState.RECORDING,
) -> dict[str, Any]:
    return build_tool_success(
        TOOL_START_LISTENING,
        {
            "session_id": session_id,
            "device_id": device_id,
            "sample_rate": sample_rate,
            "state": state.value,
            "mode": "rolling",
            "duration_seconds": duration_seconds,
        },
    )


def start_listening_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_START_LISTENING, code, message, details)


def _build_poll_transcription_data(
    session_id: str,
    transcript: str,
    duration_seconds: int,
    completed_windows: int,
    transcript_updated_at: str | None,
    state: LifecycleState,
) -> dict[str, Any]:
    status = (
        "pending"
        if completed_windows == 0 and transcript == "" and transcript_updated_at is None
        else "ready"
    )
    return {
        "session_id": session_id,
        "status": status,
        "transcript": transcript,
        "state": state.value,
        "duration_seconds": duration_seconds,
        "completed_windows": completed_windows,
        "transcript_updated_at": transcript_updated_at,
    }


def poll_transcription_success(
    session_id: str,
    transcript: str,
    duration_seconds: int,
    completed_windows: int,
    transcript_updated_at: str | None,
    state: LifecycleState = LifecycleState.IDLE,
) -> dict[str, Any]:
    return build_tool_success(
        TOOL_POLL_TRANSCRIPTION,
        _build_poll_transcription_data(
            session_id=session_id,
            transcript=transcript,
            duration_seconds=duration_seconds,
            completed_windows=completed_windows,
            transcript_updated_at=transcript_updated_at,
            state=state,
        ),
    )


def poll_transcription_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_POLL_TRANSCRIPTION, code, message, details)


def stop_listening_success(
    session_id: str,
    transcript: str,
    duration_seconds: int,
    completed_windows: int,
    transcript_updated_at: str | None,
    state: LifecycleState = LifecycleState.IDLE,
) -> dict[str, Any]:
    data = _build_poll_transcription_data(
        session_id=session_id,
        transcript=transcript,
        duration_seconds=duration_seconds,
        completed_windows=completed_windows,
        transcript_updated_at=transcript_updated_at,
        state=state,
    )
    data.update({"deprecated": True, "replacement": TOOL_POLL_TRANSCRIPTION})
    return build_tool_success(
        TOOL_STOP_LISTENING,
        data,
    )


def stop_listening_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_STOP_LISTENING, code, message, details)


def speak_text_success(characters: int) -> dict[str, Any]:
    return build_tool_success(
        TOOL_SPEAK_TEXT,
        {
            "spoken": True,
            "backend": "espeak-ng",
            "characters": characters,
        },
    )


def speak_text_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_SPEAK_TEXT, code, message, details)


def get_server_status_success(
    state: LifecycleState,
    active_session_id: str | None,
) -> dict[str, Any]:
    return build_tool_success(
        TOOL_GET_SERVER_STATUS,
        {
            "state": state.value,
            "active_session_id": active_session_id,
        },
    )


def get_server_status_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_tool_error(TOOL_GET_SERVER_STATUS, code, message, details)
