"""Session orchestration for recording lifecycle and transcript handoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import threading
from typing import Callable, Protocol
from uuid import uuid4

from speaktome_mcp.audio import AudioCapture, AudioRecordingSession, CapturedAudio
from speaktome_mcp.contracts import (
    ERROR_NO_ACTIVE_SESSION,
    ERROR_SESSION_MISMATCH,
    LifecycleState,
    ToolContractError,
    poll_transcription_error,
    poll_transcription_success,
    start_listening_success,
    stop_listening_error,
    stop_listening_success,
)
from speaktome_mcp.state import ServerStateMachine
from speaktome_mcp.transcription import AudioBuffer, TranscriptionService


def _generate_session_id() -> str:
    return str(uuid4())


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class CompletedTranscriptSnapshot:
    transcript: str
    completed_windows: int
    transcript_updated_at: str | None


class LatestCompletedTranscript(Protocol):
    @property
    def transcript(self) -> str: ...

    @property
    def completed_windows(self) -> int: ...

    @property
    def transcript_updated_at(self) -> str | None: ...


class RollingTranscriptionSession(Protocol):
    device_id: int
    sample_rate: int
    duration_seconds: int

    def stop(self) -> LatestCompletedTranscript | None:
        """Stop future work, discard in-progress capture, and return the latest complete window."""


@dataclass(slots=True)
class _ActiveSession:
    session_id: str
    device_id: int
    sample_rate: int
    duration_seconds: int
    rolling_session: RollingTranscriptionSession


class _BackgroundRollingTranscriptionSession:
    def __init__(
        self,
        *,
        audio_capture: AudioCapture,
        transcription_service: TranscriptionService,
        duration_seconds: int,
        device_id: int | None,
        sample_rate: int | None,
        timestamp_factory: Callable[[], str] = _utc_now_isoformat,
    ) -> None:
        self.duration_seconds = duration_seconds
        self._audio_capture = audio_capture
        self._transcription_service = transcription_service
        self._timestamp_factory = timestamp_factory
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_completed: CompletedTranscriptSnapshot | None = None
        self._failure: Exception | None = None
        self._current_recording_session = audio_capture.start_recording(
            device_id=device_id,
            sample_rate=sample_rate,
        )
        self.device_id = self._current_recording_session.device_id
        self.sample_rate = self._current_recording_session.sample_rate
        self._thread = threading.Thread(
            target=self._run,
            args=(self._current_recording_session,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> LatestCompletedTranscript | None:
        self._stop_event.set()
        with self._lock:
            current_recording_session = self._current_recording_session
            latest_completed = self._latest_completed

        if current_recording_session is None:
            return latest_completed

        self._thread.join()
        if self._failure is not None:
            raise self._failure
        return self._latest_completed

    def _run(self, recording_session: AudioRecordingSession) -> None:
        active_recording = recording_session
        try:
            while True:
                if self._stop_event.wait(self.duration_seconds):
                    self._stop_recording_session(active_recording)
                    return

                with self._lock:
                    self._current_recording_session = None

                captured_audio = active_recording.stop()
                transcript = self._transcription_service.transcribe(
                    self._build_audio_buffer(captured_audio)
                )
                if self._stop_event.is_set():
                    return

                completed_windows = 1
                if self._latest_completed is not None:
                    completed_windows = self._latest_completed.completed_windows + 1
                self._latest_completed = CompletedTranscriptSnapshot(
                    transcript=transcript,
                    completed_windows=completed_windows,
                    transcript_updated_at=self._timestamp_factory(),
                )
                active_recording = self._audio_capture.start_recording(
                    device_id=self.device_id,
                    sample_rate=self.sample_rate,
                )
                with self._lock:
                    self._current_recording_session = active_recording
        except Exception as exc:
            self._failure = exc
            self._stop_current_recording_session_quietly()
        finally:
            with self._lock:
                self._current_recording_session = None

    def _stop_recording_session(self, recording_session: AudioRecordingSession) -> None:
        recording_session.stop()
        with self._lock:
            self._current_recording_session = None

    def _stop_current_recording_session_quietly(self) -> None:
        with self._lock:
            recording_session = self._current_recording_session
            self._current_recording_session = None

        if recording_session is None:
            return

        try:
            recording_session.stop()
        except Exception:
            pass

    def _build_audio_buffer(self, captured_audio: CapturedAudio) -> AudioBuffer:
        return AudioBuffer(
            data=captured_audio.pcm_frames,
            sample_rate=captured_audio.sample_rate,
            format="pcm_s16le",
            channels=captured_audio.channels,
            sample_width=captured_audio.sample_width_bytes,
        )


class SessionManager:
    """Coordinate rolling recording sessions between state and transcription."""

    def __init__(
        self,
        *,
        state_machine: ServerStateMachine,
        audio_capture: AudioCapture,
        transcription_service: TranscriptionService,
        rolling_session_factory: Callable[..., RollingTranscriptionSession] | None = None,
        session_id_factory: Callable[[], str] = _generate_session_id,
    ) -> None:
        self._state_machine = state_machine
        self._audio_capture = audio_capture
        self._transcription_service = transcription_service
        self._rolling_session_factory = rolling_session_factory or self._start_background_session
        self._session_id_factory = session_id_factory
        self._active_session: _ActiveSession | None = None

    def get_server_status(self) -> dict[str, object]:
        """Return the current lifecycle snapshot."""

        return self._state_machine.get_status()

    @property
    def has_active_session(self) -> bool:
        """Return whether session-local state is currently retained."""

        return self._active_session is not None

    @property
    def has_buffered_audio(self) -> bool:
        """Rolling mode does not retain a separate transcription handoff buffer."""

        return False

    def start_listening(
        self,
        *,
        duration_seconds: int,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> dict[str, object]:
        """Start a rolling listening session and return immediately."""

        session_id = self._session_id_factory()
        self._state_machine.start_listening(session_id)

        try:
            rolling_session = self._rolling_session_factory(
                duration_seconds=duration_seconds,
                device_id=device_id,
                sample_rate=sample_rate,
            )
        except Exception:
            self._cleanup_after_start_failure(session_id)
            raise

        self._active_session = _ActiveSession(
            session_id=session_id,
            device_id=rolling_session.device_id,
            sample_rate=rolling_session.sample_rate,
            duration_seconds=duration_seconds,
            rolling_session=rolling_session,
        )
        return start_listening_success(
            session_id=session_id,
            device_id=rolling_session.device_id,
            sample_rate=rolling_session.sample_rate,
            duration_seconds=duration_seconds,
            state=LifecycleState.RECORDING,
        )

    def poll_transcription(self, session_id: str) -> dict[str, object]:
        """Stop rolling work and return the latest completed transcription window."""

        return self._stop_and_collect(
            session_id=session_id,
            transition=self._state_machine.poll_transcription,
            payload_builder=poll_transcription_success,
            error_builder=poll_transcription_error,
            missing_message="Cannot poll transcription because no active session exists.",
            mismatch_message="Cannot poll transcription for a different session.",
        )

    def stop_listening(self, session_id: str) -> dict[str, object]:
        """Deprecated alias for poll_transcription."""

        return self._stop_and_collect(
            session_id=session_id,
            transition=self._state_machine.stop_listening,
            payload_builder=stop_listening_success,
            error_builder=stop_listening_error,
            missing_message="Cannot stop listening because no active session exists.",
            mismatch_message="Cannot stop listening for a different session.",
        )

    def _stop_and_collect(
        self,
        *,
        session_id: str,
        transition: Callable[[str], None],
        payload_builder: Callable[..., dict[str, object]],
        error_builder: Callable[[str, str, dict[str, object] | None], dict[str, object]],
        missing_message: str,
        mismatch_message: str,
    ) -> dict[str, object]:
        active_session = self._require_active_session(
            session_id,
            error_builder=error_builder,
            missing_message=missing_message,
            mismatch_message=mismatch_message,
        )
        transition(session_id)

        try:
            latest_completed = active_session.rolling_session.stop()
        finally:
            self._clear_session_data()

        if latest_completed is None:
            return payload_builder(
                session_id=session_id,
                transcript="",
                duration_seconds=active_session.duration_seconds,
                completed_windows=0,
                transcript_updated_at=None,
                state=LifecycleState.IDLE,
            )

        return payload_builder(
            session_id=session_id,
            transcript=latest_completed.transcript,
            duration_seconds=active_session.duration_seconds,
            completed_windows=latest_completed.completed_windows,
            transcript_updated_at=latest_completed.transcript_updated_at,
            state=LifecycleState.IDLE,
        )

    def _require_active_session(
        self,
        session_id: str,
        *,
        error_builder: Callable[[str, str, dict[str, object] | None], dict[str, object]],
        missing_message: str,
        mismatch_message: str,
    ) -> _ActiveSession:
        active_session_id = self._state_machine.active_session_id
        if self._state_machine.state is LifecycleState.IDLE or active_session_id is None:
            raise ToolContractError(
                error_builder(
                    ERROR_NO_ACTIVE_SESSION,
                    missing_message,
                    {
                        "current_state": self._state_machine.state.value,
                    },
                )
            )

        if session_id != active_session_id:
            raise ToolContractError(
                error_builder(
                    ERROR_SESSION_MISMATCH,
                    mismatch_message,
                    {
                        "active_session_id": active_session_id,
                        "requested_session_id": session_id,
                    },
                )
            )

        if self._active_session is None or self._active_session.session_id != session_id:
            raise ToolContractError(
                error_builder(
                    ERROR_NO_ACTIVE_SESSION,
                    missing_message,
                    {
                        "current_state": self._state_machine.state.value,
                    },
                )
            )

        return self._active_session

    def _cleanup_after_start_failure(self, session_id: str) -> None:
        self._state_machine.abort_session(session_id)
        self._clear_session_data()

    def _clear_session_data(self) -> None:
        self._active_session = None

    def _start_background_session(
        self,
        *,
        duration_seconds: int,
        device_id: int | None = None,
        sample_rate: int | None = None,
    ) -> RollingTranscriptionSession:
        return _BackgroundRollingTranscriptionSession(
            audio_capture=self._audio_capture,
            transcription_service=self._transcription_service,
            duration_seconds=duration_seconds,
            device_id=device_id,
            sample_rate=sample_rate,
        )


__all__ = ["CompletedTranscriptSnapshot", "SessionManager"]
