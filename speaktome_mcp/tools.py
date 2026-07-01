"""Thin MCP tool handlers that validate inputs and serialize contract payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from speaktome_mcp.audio import AudioCapture, AudioInputDevice
from speaktome_mcp.contracts import (
    ERROR_INVALID_ARGUMENT,
    ERROR_RUNTIME_FAILURE,
    TOOL_GET_SERVER_STATUS,
    TOOL_LIST_MICROPHONE_DEVICES,
    TOOL_START_LISTENING,
    TOOL_STOP_LISTENING,
    ToolContractError,
    get_server_status_error,
    list_microphone_devices_error,
    list_microphone_devices_success,
    start_listening_error,
    stop_listening_error,
)
from speaktome_mcp.session import SessionManager


ToolPayload = dict[str, Any]
ToolHandlerProvider = Callable[[], "SpeakToMeToolHandlers"]


@dataclass(slots=True)
class SpeakToMeToolHandlers:
    """Finalized MCP tool handlers delegating to audio/session abstractions."""

    audio_capture: AudioCapture
    session_manager: SessionManager

    def list_microphone_devices(self) -> ToolPayload:
        try:
            devices = [self._serialize_device(device) for device in self.audio_capture.list_input_devices()]
        except ToolContractError as exc:
            return exc.payload
        except Exception as exc:
            return self._runtime_error(
                tool=TOOL_LIST_MICROPHONE_DEVICES,
                message="Failed to list microphone devices.",
                exc=exc,
            )

        return list_microphone_devices_success(devices)

    def start_listening(
        self,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> ToolPayload:
        try:
            validated_device_id = self._validate_optional_non_negative_int(
                tool=TOOL_START_LISTENING,
                field_name="device_id",
                value=device_id,
            )
            validated_sample_rate = self._validate_optional_positive_int(
                tool=TOOL_START_LISTENING,
                field_name="sample_rate",
                value=sample_rate,
            )
            return self.session_manager.start_listening(
                device_id=validated_device_id,
                sample_rate=validated_sample_rate,
            )
        except ToolContractError as exc:
            return exc.payload
        except Exception as exc:
            return self._runtime_error(
                tool=TOOL_START_LISTENING,
                message="Failed to start listening.",
                exc=exc,
            )

    def stop_listening(self, session_id: str) -> ToolPayload:
        try:
            validated_session_id = self._validate_session_id(session_id)
            return self.session_manager.stop_listening(validated_session_id)
        except ToolContractError as exc:
            return exc.payload
        except Exception as exc:
            return self._runtime_error(
                tool=TOOL_STOP_LISTENING,
                message="Failed to stop listening.",
                exc=exc,
            )

    def get_server_status(self) -> ToolPayload:
        try:
            return self.session_manager.get_server_status()
        except ToolContractError as exc:
            return exc.payload
        except Exception as exc:
            return self._runtime_error(
                tool=TOOL_GET_SERVER_STATUS,
                message="Failed to get server status.",
                exc=exc,
            )

    def _serialize_device(self, device: AudioInputDevice) -> dict[str, Any]:
        return {
            "id": device.device_id,
            "name": device.name,
            "max_input_channels": device.max_input_channels,
            "default_sample_rate": device.default_sample_rate,
            "is_default": device.is_default,
        }

    def _validate_session_id(self, value: object) -> str:
        if isinstance(value, str) and value.strip():
            return value

        raise ToolContractError(
            stop_listening_error(
                ERROR_INVALID_ARGUMENT,
                "session_id must be a non-empty string.",
                {
                    "field": "session_id",
                    "value": value,
                },
            )
        )

    def _validate_optional_non_negative_int(
        self,
        *,
        tool: str,
        field_name: str,
        value: object,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ToolContractError(
                self._invalid_argument_error(
                    tool=tool,
                    field_name=field_name,
                    value=value,
                    expectation="a non-negative integer or null",
                )
            )

        return value

    def _validate_optional_positive_int(
        self,
        *,
        tool: str,
        field_name: str,
        value: object,
    ) -> int | None:
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ToolContractError(
                self._invalid_argument_error(
                    tool=tool,
                    field_name=field_name,
                    value=value,
                    expectation="a positive integer or null",
                )
            )

        return value

    def _invalid_argument_error(
        self,
        *,
        tool: str,
        field_name: str,
        value: object,
        expectation: str,
    ) -> ToolPayload:
        message = f"{field_name} must be {expectation}."
        details = {
            "field": field_name,
            "value": value,
        }

        if tool == TOOL_START_LISTENING:
            return start_listening_error(ERROR_INVALID_ARGUMENT, message, details)
        if tool == TOOL_STOP_LISTENING:
            return stop_listening_error(ERROR_INVALID_ARGUMENT, message, details)
        if tool == TOOL_LIST_MICROPHONE_DEVICES:
            return list_microphone_devices_error(ERROR_INVALID_ARGUMENT, message, details)
        return get_server_status_error(ERROR_INVALID_ARGUMENT, message, details)

    def _runtime_error(self, *, tool: str, message: str, exc: Exception) -> ToolPayload:
        details = {
            "exception_type": exc.__class__.__name__,
            "reason": str(exc),
        }

        if tool == TOOL_LIST_MICROPHONE_DEVICES:
            return list_microphone_devices_error(ERROR_RUNTIME_FAILURE, message, details)
        if tool == TOOL_START_LISTENING:
            return start_listening_error(ERROR_RUNTIME_FAILURE, message, details)
        if tool == TOOL_STOP_LISTENING:
            return stop_listening_error(ERROR_RUNTIME_FAILURE, message, details)
        return get_server_status_error(ERROR_RUNTIME_FAILURE, message, details)


def register_tools(server: FastMCP, handler_provider: ToolHandlerProvider) -> None:
    """Register the finalized SpeakToMe MCP tool surface on the server."""

    @server.tool(name=TOOL_LIST_MICROPHONE_DEVICES, structured_output=True)
    def list_microphone_devices() -> ToolPayload:
        return handler_provider().list_microphone_devices()

    @server.tool(name=TOOL_START_LISTENING, structured_output=True)
    def start_listening(
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> ToolPayload:
        return handler_provider().start_listening(device_id=device_id, sample_rate=sample_rate)

    @server.tool(name=TOOL_STOP_LISTENING, structured_output=True)
    def stop_listening(session_id: str) -> ToolPayload:
        return handler_provider().stop_listening(session_id=session_id)

    @server.tool(name=TOOL_GET_SERVER_STATUS, structured_output=True)
    def get_server_status() -> ToolPayload:
        return handler_provider().get_server_status()


__all__ = ["SpeakToMeToolHandlers", "register_tools"]
