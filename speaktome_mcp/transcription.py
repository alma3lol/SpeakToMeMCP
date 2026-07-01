"""Transcription service abstractions and faster-whisper integration."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import io
import wave
from typing import Any, BinaryIO, Callable, Iterable, Protocol


DEFAULT_MODEL_SIZE = "small"


class TranscriptionError(RuntimeError):
    """Raised when transcription fails."""


class ModelStartupError(TranscriptionError):
    """Raised when the transcription model cannot be loaded at startup."""


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """In-memory audio payload for transcription.

    `format` supports either WAV bytes or raw signed 16-bit PCM bytes.
    """

    data: bytes
    sample_rate: int
    format: str = "wav"
    channels: int = 1
    sample_width: int = 2

    def as_binary_stream(self) -> BinaryIO:
        """Return the audio as a seekable WAV stream."""
        if self.format == "wav":
            return io.BytesIO(self.data)
        if self.format != "pcm_s16le":
            msg = f"Unsupported audio format: {self.format}"
            raise ValueError(msg)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(self.data)
        wav_buffer.seek(0)
        return wav_buffer


class TranscriptionService(Protocol):
    """Service interface for converting in-memory audio into plain text."""

    def transcribe(self, audio: AudioBuffer) -> str:
        """Return normalized transcript text for the provided audio."""


def normalize_transcript_text(text: str) -> str:
    """Collapse transcript whitespace into a stable plain-text result."""
    return " ".join(text.split())


def _build_whisper_model(
    *,
    model_size: str,
    device: str = "auto",
    compute_type: str = "default",
) -> Any:
    whisper_module = import_module("faster_whisper")
    whisper_model = getattr(whisper_module, "WhisperModel")
    return whisper_model(model_size, device=device, compute_type=compute_type)


def load_transcription_service(
    *,
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = "auto",
    compute_type: str = "default",
    model_factory: Callable[..., Any] | None = None,
) -> "FasterWhisperTranscriptionService":
    """Create the eager-loaded faster-whisper service for startup wiring."""
    return FasterWhisperTranscriptionService.create(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        model_factory=model_factory,
    )


class FasterWhisperTranscriptionService:
    """Concrete transcriber that reuses a single eager-loaded Whisper model."""

    def __init__(self, model: Any) -> None:
        self._model = model

    @classmethod
    def create(
        cls,
        *,
        model_size: str = DEFAULT_MODEL_SIZE,
        device: str = "auto",
        compute_type: str = "default",
        model_factory: Callable[..., Any] | None = None,
    ) -> "FasterWhisperTranscriptionService":
        factory = model_factory or _build_whisper_model
        try:
            model = factory(
                model_size=model_size,
                device=device,
                compute_type=compute_type,
            )
        except Exception as exc:  # pragma: no cover - exercised in tests via fake factory
            msg = f"Failed to load faster-whisper model '{model_size}' during startup"
            raise ModelStartupError(msg) from exc
        return cls(model=model)

    def transcribe(self, audio: AudioBuffer) -> str:
        try:
            segments, _info = self._model.transcribe(audio.as_binary_stream())
        except Exception as exc:  # pragma: no cover - depends on backend failure modes
            raise TranscriptionError("faster-whisper transcription failed") from exc

        text = _collect_segment_text(segments)
        return normalize_transcript_text(text)


def _collect_segment_text(segments: Iterable[Any]) -> str:
    return " ".join(str(getattr(segment, "text", "")) for segment in segments)
