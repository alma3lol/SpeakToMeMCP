"""Session orchestration for recording lifecycle and transcript handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from speaktome_mcp.audio import AudioCapture, AudioRecordingSession, CapturedAudio
from speaktome_mcp.contracts import (
    ERROR_INVALID_STATE,
    ERROR_NO_ACTIVE_SESSION,
    ERROR_SESSION_MISMATCH,
    LifecycleState,
    ToolContractError,
    start_listening_success,
    stop_listening_error,
    stop_listening_success,
)
from speaktome_mcp.state import ServerStateMachine
from speaktome_mcp.transcription import AudioBuffer, TranscriptionService


def _generate_session_id() -> str:
    return str(uuid4())


@dataclass(slots=True)
class _ActiveSession:
    session_id: str
    device_id: int
    recording_session: AudioRecordingSession


class SessionManager:
    """Coordinate recording sessions between state, audio capture, and transcription."""

    def __init__(
        self,
        *,
        state_machine: ServerStateMachine,
        audio_capture: AudioCapture,
        transcription_service: TranscriptionService,
        session_id_factory: Callable[[], str] = _generate_session_id,
    ) -> None:
        self._state_machine = state_machine
        self._audio_capture = audio_capture
        self._transcription_service = transcription_service
        self._session_id_factory = session_id_factory
        self._active_session: _ActiveSession | None = None
        self._buffered_audio: AudioBuffer | None = None

    def get_server_status(self) -> dict[str, object]:
        """Return the current lifecycle snapshot."""

        return self._state_machine.get_status()

    @property
    def has_active_session(self) -> bool:
        """Return whether session-local state is currently retained."""

        return self._active_session is not None

    @property
    def has_buffered_audio(self) -> bool:
        """Return whether a transcription handoff buffer is currently retained."""

        return self._buffered_audio is not None

    def start_listening(
        self,
        *,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> dict[str, object]:
        """Start recording a single active listening session."""

        session_id = self._session_id_factory()
        self._state_machine.start_listening(session_id)

        try:
            recording_session = self._audio_capture.start_recording(
                device_id=device_id,
                sample_rate=sample_rate,
            )
        except Exception:
            self._cleanup_after_failure(session_id)
            raise

        self._active_session = _ActiveSession(
            session_id=session_id,
            device_id=recording_session.device_id,
            recording_session=recording_session,
        )
        self._buffered_audio = None
        return start_listening_success(
            session_id=session_id,
            device_id=recording_session.device_id,
            sample_rate=recording_session.sample_rate,
            state=LifecycleState.RECORDING,
        )

    def stop_listening(self, session_id: str) -> dict[str, object]:
        """Stop the active recording, transcribe once, and return the transcript."""

        active_session = self._require_active_session(session_id)

        try:
            captured_audio = active_session.recording_session.stop()
            self._buffered_audio = self._build_audio_buffer(captured_audio)
            self._state_machine.stop_listening(session_id)
            transcript = self._transcription_service.transcribe(self._buffered_audio)
            self._state_machine.finish_transcription(session_id)
        except Exception:
            self._cleanup_after_failure(session_id)
            raise

        self._clear_session_data()
        return stop_listening_success(
            session_id=session_id,
            transcript=transcript,
            state=LifecycleState.IDLE,
        )

    def _require_active_session(self, session_id: str) -> _ActiveSession:
        active_session_id = self._state_machine.active_session_id
        if self._state_machine.state is LifecycleState.IDLE or active_session_id is None:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_NO_ACTIVE_SESSION,
                    "Cannot stop listening because no active session exists.",
                    {
                        "current_state": self._state_machine.state.value,
                    },
                )
            )

        if self._state_machine.state is not LifecycleState.RECORDING:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_INVALID_STATE,
                    "Cannot stop listening unless the server is recording.",
                    {
                        "current_state": self._state_machine.state.value,
                        "expected_state": LifecycleState.RECORDING.value,
                        "active_session_id": active_session_id,
                    },
                )
            )

        if session_id != active_session_id:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_SESSION_MISMATCH,
                    "Cannot stop listening for a different session.",
                    {
                        "active_session_id": active_session_id,
                        "requested_session_id": session_id,
                    },
                )
            )

        if self._active_session is None or self._active_session.session_id != session_id:
            raise ToolContractError(
                stop_listening_error(
                    ERROR_NO_ACTIVE_SESSION,
                    "Cannot stop listening because no active session exists.",
                    {
                        "current_state": self._state_machine.state.value,
                    },
                )
            )

        return self._active_session

    def _build_audio_buffer(self, captured_audio: CapturedAudio) -> AudioBuffer:
        return AudioBuffer(
            data=captured_audio.pcm_frames,
            sample_rate=captured_audio.sample_rate,
            format="pcm_s16le",
            channels=captured_audio.channels,
            sample_width=captured_audio.sample_width_bytes,
        )

    def _cleanup_after_failure(self, session_id: str) -> None:
        try:
            if self._state_machine.active_session_id != session_id:
                return

            if self._state_machine.state is LifecycleState.RECORDING:
                self._state_machine.stop_listening(session_id)

            if self._state_machine.state is LifecycleState.TRANSCRIBING:
                self._state_machine.finish_transcription(session_id)
        finally:
            self._clear_session_data()

    def _clear_session_data(self) -> None:
        self._active_session = None
        self._buffered_audio = None


__all__ = ["SessionManager"]
