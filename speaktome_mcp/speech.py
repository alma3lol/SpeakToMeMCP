"""Speech service abstractions and local espeak-ng integration."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Protocol


DEFAULT_SPEECH_TIMEOUT_SECONDS = 10.0


class SpeechError(RuntimeError):
    """Raised when speech synthesis fails."""


class SpeechExecutableNotFoundError(SpeechError):
    """Raised when the espeak-ng executable is unavailable."""


@dataclass(frozen=True, slots=True)
class SpeechCommandError(SpeechError):
    """Raised when espeak-ng exits unsuccessfully."""

    returncode: int
    stderr: str = ""

    def __str__(self) -> str:
        detail = self.stderr.strip() or "espeak-ng exited with a non-zero status"
        return f"espeak-ng failed with exit code {self.returncode}: {detail}"


class SpeechTimeoutError(SpeechError):
    """Raised when espeak-ng does not finish before the timeout."""


class SpeechService(Protocol):
    """Service interface for speaking plain text locally."""

    def speak(self, text: str) -> None:
        """Speak the provided plain text."""


class SpeechCommandRunner(Protocol):
    """Typed subprocess seam for executing the speech backend."""

    def __call__(
        self,
        args: list[str],
        /,
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        """Execute the provided argv and return the completed process."""
        ...


def _run_command(
    args: list[str],
    /,
    *,
    input: str,
    text: bool,
    capture_output: bool,
    check: bool,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input,
        text=text,
        capture_output=capture_output,
        check=check,
        timeout=timeout,
    )


class EspeakSpeechService:
    """Concrete speech backend that pipes text into local espeak-ng."""

    def __init__(
        self,
        *,
        executable: str = "espeak-ng",
        timeout_seconds: float = DEFAULT_SPEECH_TIMEOUT_SECONDS,
        command_runner: SpeechCommandRunner | None = None,
    ) -> None:
        self._executable: str = executable
        self._timeout_seconds: float = timeout_seconds
        self._command_runner: SpeechCommandRunner = command_runner or _run_command

    def speak(self, text: str) -> None:
        argv = [self._executable, "--stdin"]
        try:
            result = self._command_runner(
                argv,
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            msg = f"espeak-ng executable '{self._executable}' was not found"
            raise SpeechExecutableNotFoundError(msg) from exc
        except subprocess.TimeoutExpired as exc:
            msg = f"espeak-ng timed out after {self._timeout_seconds} seconds"
            raise SpeechTimeoutError(msg) from exc

        if result.returncode != 0:
            raise SpeechCommandError(returncode=result.returncode, stderr=result.stderr)
