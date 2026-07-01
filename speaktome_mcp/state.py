"""Lifecycle state machine for the SpeakToMe MCP server."""

from __future__ import annotations

from dataclasses import dataclass

from speaktome_mcp.contracts import (
    ERROR_INVALID_STATE,
    ERROR_NO_ACTIVE_SESSION,
    ERROR_SESSION_MISMATCH,
    LifecycleState,
    ToolContractError,
    get_server_status_success,
    start_listening_error,
    stop_listening_error,
)


@dataclass(slots=True)
class ServerStateMachine:
    """Enforce deterministic lifecycle transitions for a single active session."""

    state: LifecycleState = LifecycleState.IDLE
    active_session_id: str | None = None

    def get_status(self) -> dict[str, object]:
        """Return a side-effect-free status snapshot."""

        return get_server_status_success(self.state, self.active_session_id)

    def start_listening(self, session_id: str) -> None:
        """Move from idle to recording for a new session."""

        if self.state is not LifecycleState.IDLE:
            raise ToolContractError(
                start_listening_error(
                    ERROR_INVALID_STATE,
                    "Cannot start listening unless the server is idle.",
                    {
                        "current_state": self.state.value,
                        "expected_state": LifecycleState.IDLE.value,
                    },
                )
            )

        self.state = LifecycleState.RECORDING
        self.active_session_id = session_id

    def stop_listening(self, session_id: str) -> None:
        """Move from recording to transcribing for the active session."""

        if self.state is LifecycleState.IDLE or self.active_session_id is None:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_NO_ACTIVE_SESSION,
                    "Cannot stop listening because no active session exists.",
                    {
                        "current_state": self.state.value,
                    },
                )
            )

        if self.state is not LifecycleState.RECORDING:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_INVALID_STATE,
                    "Cannot stop listening unless the server is recording.",
                    {
                        "current_state": self.state.value,
                        "expected_state": LifecycleState.RECORDING.value,
                        "active_session_id": self.active_session_id,
                    },
                )
            )

        if session_id != self.active_session_id:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_SESSION_MISMATCH,
                    "Cannot stop listening for a different session.",
                    {
                        "active_session_id": self.active_session_id,
                        "requested_session_id": session_id,
                    },
                )
            )

        self.state = LifecycleState.TRANSCRIBING

    def finish_transcription(self, session_id: str) -> None:
        """Move from transcribing back to idle after the active session completes."""

        if self.state is not LifecycleState.TRANSCRIBING or self.active_session_id is None:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_INVALID_STATE,
                    "Cannot finish transcription unless the server is transcribing.",
                    {
                        "current_state": self.state.value,
                        "expected_state": LifecycleState.TRANSCRIBING.value,
                    },
                )
            )

        if session_id != self.active_session_id:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_SESSION_MISMATCH,
                    "Cannot finish transcription for a different session.",
                    {
                        "active_session_id": self.active_session_id,
                        "requested_session_id": session_id,
                    },
                )
            )

        self.state = LifecycleState.IDLE
        self.active_session_id = None
