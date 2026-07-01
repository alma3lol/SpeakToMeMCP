from __future__ import annotations

import pytest

from speaktome_mcp.transcription import FasterWhisperTranscriptionService
from speaktome_mcp.transcription import ModelStartupError
from speaktome_mcp.transcription import load_transcription_service


class FakeStartupModel:
    def transcribe(self, _audio_stream):
        return iter(()), None


def test_eager_load_uses_small_model_by_default_and_returns_service() -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_factory(*, model_size: str, device: str, compute_type: str) -> FakeStartupModel:
        calls.append((model_size, device, compute_type))
        return FakeStartupModel()

    service = load_transcription_service(model_factory=fake_factory)

    assert isinstance(service, FasterWhisperTranscriptionService)
    assert calls == [("small", "auto", "default")]


def test_failure_model_startup_surfaces_clean_error() -> None:
    def failing_factory(*, model_size: str, device: str, compute_type: str) -> FakeStartupModel:
        raise RuntimeError(f"unable to load {model_size}")

    with pytest.raises(ModelStartupError, match="small") as exc_info:
        load_transcription_service(model_factory=failing_factory)

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_model_instance_is_reused_for_multiple_transcriptions() -> None:
    created_models: list[FakeReusableModel] = []

    def fake_factory(*, model_size: str, device: str, compute_type: str) -> "FakeReusableModel":
        model = FakeReusableModel()
        created_models.append(model)
        return model

    service = load_transcription_service(model_factory=fake_factory)
    service.transcribe(FakeReusableModel.audio())
    service.transcribe(FakeReusableModel.audio())

    assert len(created_models) == 1
    assert created_models[0].calls == 2


class FakeReusableModel:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, _audio_stream):
        self.calls += 1
        return iter(()), None

    @staticmethod
    def audio():
        from speaktome_mcp.transcription import AudioBuffer

        return AudioBuffer(data=b"RIFFfake", sample_rate=16_000, format="wav")
