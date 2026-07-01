"""Lifecycle state machine for the SpeakToMe MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from speaktome_mcp.contracts import (
    ERROR_INVALID_STATE,
    ERROR_NO_ACTIVE_SESSION,
    ERROR_SESSION_MISMATCH,
    LifecycleState,
    ToolContractError,
    get_server_status_success,
    poll_transcription_error,
    start_listening_error,
    stop_listening_error,
)


ErrorBuilder = Callable[[str, str, dict[str, object] | None], dict[str, object]]


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

    def poll_transcription(self, session_id: str) -> None:
        """Move from recording to idle while stopping the rolling session."""

        self._complete_active_session(
            session_id=session_id,
            error_builder=poll_transcription_error,
            missing_message="Cannot poll transcription because no active session exists.",
            mismatch_message="Cannot poll transcription for a different session.",
        )

    def stop_listening(self, session_id: str) -> None:
        """Deprecated alias for poll_transcription with stop_listening payloads."""

        self._complete_active_session(
            session_id=session_id,
            error_builder=stop_listening_error,
            missing_message="Cannot stop listening because no active session exists.",
            mismatch_message="Cannot stop listening for a different session.",
        )

    def abort_session(self, session_id: str) -> None:
        """Best-effort reset used when startup or worker failures occur."""

        if self.active_session_id == session_id:
            self.state = LifecycleState.IDLE
            self.active_session_id = None

    def finish_transcription(self, session_id: str) -> None:
        """Retained for compatibility with older callers."""

        self.abort_session(session_id)

    def _complete_active_session(
        self,
        *,
        session_id: str,
        error_builder: ErrorBuilder,
        missing_message: str,
        mismatch_message: str,
    ) -> None:
        if self.state is LifecycleState.IDLE or self.active_session_id is None:
            raise ToolContractError(
                error_builder(
                    ERROR_NO_ACTIVE_SESSION,
                    missing_message,
                    {
                        "current_state": self.state.value,
                    },
                )
            )

        if self.state is not LifecycleState.RECORDING:
            raise ToolContractError(
                error_builder(
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
                error_builder(
                    ERROR_SESSION_MISMATCH,
                    mismatch_message,
                    {
                        "active_session_id": self.active_session_id,
                        "requested_session_id": session_id,
                    },
                )
            )

        self.state = LifecycleState.IDLE
        self.active_session_id = None
