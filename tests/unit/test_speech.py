from __future__ import annotations

import subprocess

import pytest

from speaktome_mcp.speech import EspeakSpeechService
from speaktome_mcp.speech import SpeechCommandError
from speaktome_mcp.speech import SpeechExecutableNotFoundError
from speaktome_mcp.speech import SpeechTimeoutError
from tests.fakes import FakeCommandRunner
from tests.fakes import FakeCompletedProcess


def test_speak_invokes_espeak_with_direct_argv_and_stdin() -> None:
    runner = FakeCommandRunner(
        result=FakeCompletedProcess(args=["espeak-ng", "--stdin"], returncode=0)
    )
    service = EspeakSpeechService(command_runner=runner, timeout_seconds=3.5)

    service.speak("hello from tests")

    assert runner.calls == [
        {
            "args": ["espeak-ng", "--stdin"],
            "kwargs": {
                "input": "hello from tests",
                "text": True,
                "capture_output": True,
                "check": False,
                "timeout": 3.5,
            },
        }
    ]


def test_missing_executable_raises_typed_speech_error() -> None:
    runner = FakeCommandRunner(error=FileNotFoundError("espeak-ng missing"))
    service = EspeakSpeechService(command_runner=runner)

    with pytest.raises(SpeechExecutableNotFoundError, match="espeak-ng") as exc_info:
        service.speak("hello")

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_nonzero_exit_raises_typed_speech_error() -> None:
    runner = FakeCommandRunner(
        result=FakeCompletedProcess(
            args=["espeak-ng", "--stdin"],
            returncode=2,
            stderr="audio backend failed",
        )
    )
    service = EspeakSpeechService(command_runner=runner)

    with pytest.raises(SpeechCommandError, match="audio backend failed") as exc_info:
        service.speak("hello")

    assert exc_info.value.returncode == 2


def test_timeout_raises_typed_speech_error() -> None:
    runner = FakeCommandRunner(
        error=subprocess.TimeoutExpired(cmd=["espeak-ng", "--stdin"], timeout=5.0)
    )
    service = EspeakSpeechService(command_runner=runner, timeout_seconds=5.0)

    with pytest.raises(SpeechTimeoutError, match="timed out") as exc_info:
        service.speak("hello")

    assert isinstance(exc_info.value.__cause__, subprocess.TimeoutExpired)
