from __future__ import annotations

import pytest

from tests.fakes import (
    FakeAudioCapture,
    FakeRecordingSession,
    FakeSessionManager,
    FakeTranscriptionService,
    build_manager,
    make_audio_input_device,
    make_captured_audio,
)


@pytest.fixture
def fake_audio_input_device():
    return make_audio_input_device()


@pytest.fixture
def fake_captured_audio():
    return make_captured_audio()


@pytest.fixture
def fake_recording_session(fake_captured_audio):
    return FakeRecordingSession(captured_audio=fake_captured_audio)


@pytest.fixture
def fake_audio_capture(fake_recording_session):
    return FakeAudioCapture(recording_session=fake_recording_session)


@pytest.fixture
def fake_transcription_service():
    return FakeTranscriptionService()


@pytest.fixture
def fake_session_manager():
    return FakeSessionManager()


@pytest.fixture
def session_manager(fake_audio_capture, fake_transcription_service):
    return build_manager(
        audio_capture=fake_audio_capture,
        transcription_service=fake_transcription_service,
    )
