# Changelog

All notable changes to this project will be documented in this file.

The format is manual and follows semantic versioning for release headings.

## [Unreleased]

(Reserved for future changes.)

## [0.2.0] - 2026-07-01

### Added

- Rolling timed listening via `start_listening(duration_seconds=...)`, with `poll_transcription(session_id)` stopping the active session and returning the latest completed local transcript window.
- Local Linux-only text-to-speech via `speak_text(text)` using `espeak-ng`, alongside local microphone capture and local `faster-whisper` transcription over stdio.

### Deprecated

- `stop_listening(session_id)` as a compatibility alias for `poll_transcription(session_id)`.

## [0.1.0]

### Added

- Initial public package metadata and Linux-only stdio MCP server baseline.
