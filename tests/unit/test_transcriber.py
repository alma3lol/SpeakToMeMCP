from __future__ import annotations

from dataclasses import dataclass
import io
import wave

from speaktome_mcp.transcription import AudioBuffer
from speaktome_mcp.transcription import FasterWhisperTranscriptionService
from speaktome_mcp.transcription import TranscriptionService
from speaktome_mcp.transcription import normalize_transcript_text


@dataclass
class FakeSegment:
    text: str


class FakeModel:
    def __init__(self, segments: list[FakeSegment]) -> None:
        self._segments = segments
        self.calls: list[bytes] = []

    def transcribe(self, audio_stream):
        payload = audio_stream.read()
        self.calls.append(payload)
        audio_stream.seek(0)
        return iter(self._segments), {"language": "en"}


class FakeTranscriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def transcribe(self, audio: AudioBuffer) -> str:
        assert audio.sample_rate == 16_000
        return self.transcript


def use_transcriber(service: TranscriptionService, audio: AudioBuffer) -> str:
    return service.transcribe(audio)


def test_normalize_transcript_text_collapses_whitespace() -> None:
    assert normalize_transcript_text("  hello\n\tworld   again  ") == "hello world again"


def test_fake_transcriber_can_replace_real_service_for_tests() -> None:
    audio = AudioBuffer(data=b"wav-bytes", sample_rate=16_000)
    result = use_transcriber(FakeTranscriber("normalized transcript"), audio)
    assert result == "normalized transcript"


def test_success_pcm_audio_is_wrapped_as_wav_and_text_is_normalized() -> None:
    model = FakeModel(
        [
            FakeSegment("  hello"),
            FakeSegment("\nworld\t"),
            FakeSegment("   from   whisper  "),
        ]
    )
    service = FasterWhisperTranscriptionService(model)
    audio = AudioBuffer(
        data=(b"\x00\x00\x01\x00" * 32),
        sample_rate=16_000,
        format="pcm_s16le",
    )

    result = service.transcribe(audio)

    assert result == "hello world from whisper"
    assert model.calls[0][:4] == b"RIFF"


def test_success_blank_segments_normalize_to_empty_string() -> None:
    model = FakeModel([FakeSegment("  "), FakeSegment("\n\t")])
    service = FasterWhisperTranscriptionService(model)
    audio = AudioBuffer(data=build_wav_bytes(), sample_rate=16_000)

    result = service.transcribe(audio)

    assert result == ""


def test_success_wav_audio_is_passed_through() -> None:
    wav_bytes = build_wav_bytes()
    model = FakeModel([FakeSegment("hello")])
    service = FasterWhisperTranscriptionService(model)
    audio = AudioBuffer(data=wav_bytes, sample_rate=16_000, format="wav")

    service.transcribe(audio)

    assert model.calls[0] == wav_bytes


def build_wav_bytes() -> bytes:
    buffer = AudioBuffer(
        data=(b"\x00\x00\x01\x00" * 16),
        sample_rate=16_000,
        format="pcm_s16le",
    ).as_binary_stream()
    payload = buffer.read()
    with wave.open(io.BytesIO(payload), "rb") as wav_file:
        assert wav_file.getframerate() == 16_000
    return payload
