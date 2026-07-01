## Security Policy

## Reporting a vulnerability

If you find a security issue, use GitHub Security Advisories for this repository if that option is enabled.

If advisories are not available, open a GitHub issue and share only non-sensitive details. Do not post exploit steps, private data, recordings, or environment secrets in public.

## Supported versions

This project is currently in the `0.x` stage. Security fixes, if available, are expected to land on the latest release line rather than older `0.x` versions.

## Privacy-sensitive behavior

SpeakToMe MCP records microphone audio from the local Linux machine and transcribes it with a local `faster-whisper` model.

The current implementation keeps active audio in memory for the current session and returns the transcript to the MCP host. It is not intended to persist recordings or transcripts as a long-term store.

Model setup on first run may still require downloading model assets from external distribution infrastructure. Review your environment before using the project with sensitive audio.
