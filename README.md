# SpeakToMe MCP

SpeakToMe MCP is a local Python MCP server for Linux. It records from a microphone on the same machine, transcribes rolling audio windows with a local `faster-whisper` `small` model, and can also speak local text through `espeak-ng`, all over stdio.

## Scope

- Linux only for v1
- stdio transport only
- local microphone capture through `sounddevice`
- local transcription through `faster-whisper`
- rolling duration based listening started by `start_listening(duration_seconds=...)`
- transcript returned by `poll_transcription(session_id)` when the session is stopped
- one active in-memory session at a time
- local text to speech through `espeak-ng`

## Prerequisites

You need:

- Linux
- Python 3.11 or newer
- a working microphone input device
- system audio libraries required by `sounddevice`, usually PortAudio plus ALSA or PipeWire user-space packages on Linux
- `espeak-ng` installed if you want to use `speak_text`

If you want the `uv` workflow, install [`uv`](https://docs.astral.sh/uv/). If `sounddevice` cannot open devices, install the PortAudio runtime or development package used by your distro, then confirm your normal desktop audio stack is working. If `speak_text` fails, confirm `espeak-ng` is installed and available on `PATH` for the same Linux user session that starts the MCP host.

## Install

### Install from PyPI

```bash
pip install speaktome-mcp
```

### Install from GitHub

```bash
pip install git+https://github.com/alma3lol/SpeakToMeMCP.git
```

### Install from local source or an unpacked source archive

Download the repository source, or unpack a release source archive, then run:

```bash
pip install .
```

### Install a development environment with uv

```bash
uv sync --locked --all-extras --dev
```

## Run and verify the CLI

Installed console script:

```bash
speaktome-mcp --help
```

Start the server with the installed console script:

```bash
speaktome-mcp
```

Module entrypoint fallback:

```bash
python -m speaktome_mcp --help
```

The server only supports stdio. Running `speaktome-mcp` without extra flags starts the stdio MCP server.

## MCP host configuration

This server is meant to be launched by an MCP host that can start a stdio process.

### Example using the installed console script

```json
{
  "command": "speaktome-mcp",
  "args": []
}
```

### Example using a local uv-managed checkout

```json
{
  "command": "uv",
  "args": ["run", "speaktome-mcp"]
}
```

### Example using the module entrypoint

```json
{
  "command": "python",
  "args": ["-m", "speaktome_mcp"]
}
```

The host owns process startup and shutdown. SpeakToMe MCP does not expose a separate network service. It stays in a local stdio process and returns completed tool responses to the host.

## Startup behavior and first run expectations

The server eagerly loads the transcription backend during startup instead of waiting for the first tool call.

What that means in practice:

- startup can take longer than a minimal scaffold because the local Whisper model is prepared before the server reports ready
- first run may take noticeably longer if the `small` model is not already cached locally
- first-run model preparation or download may require network access to obtain model assets
- model load failures happen at startup, not halfway through a recording session

The runtime transcription backend is the local `faster-whisper` `small` model.

## Recording lifecycle

The server enforces one active session at a time and keeps only the latest completed rolling window:

`idle` -> `recording` -> `idle`

Important behavior:

- `start_listening(duration_seconds=N)` only works while the server is `idle`
- the server immediately starts rolling N second capture windows in the background
- only the latest completed window is retained, older completed windows are replaced
- `poll_transcription(session_id)` stops the rolling session and returns the latest completed transcript, or a pending result if no window completed yet
- `stop_listening(session_id)` is a deprecated compatibility alias for `poll_transcription(session_id)`
- audio is buffered in memory only for the active session

## Tool contract

The MCP surface exposes exactly six tools:

1. `list_microphone_devices`
2. `start_listening`
3. `poll_transcription`
4. `stop_listening`
5. `speak_text`
6. `get_server_status`

All tools return a structured envelope.

Success shape:

```json
{
  "ok": true,
  "tool": "tool_name",
  "data": {}
}
```

Error shape:

```json
{
  "ok": false,
  "tool": "tool_name",
  "error": {
    "code": "error_code",
    "message": "human readable message",
    "details": {}
  }
}
```

Known error codes used by the contract:

- `invalid_argument`
- `invalid_state`
- `no_active_session`
- `session_mismatch`
- `runtime_failure`

### `list_microphone_devices`

Arguments: none

Success data:

```json
{
  "devices": [
    {
      "id": 0,
      "name": "Built-in Microphone",
      "max_input_channels": 1,
      "default_sample_rate": 48000,
      "is_default": true
    }
  ]
}
```

Notes:

- only input-capable devices are listed
- `id` is the value to pass back into `start_listening(device_id=...)`
- `is_default` reflects the current default input device if one is available

### `start_listening`

Arguments:

- `duration_seconds: int`, required, 1 through 30
- `device_id: int | null = null`
- `sample_rate: int | null = null`

Behavior:

- if `device_id` is omitted, the server tries the default input device, then falls back to the first available input device
- if `sample_rate` is omitted, the selected device's default sample rate is used
- starts one active in-memory rolling session and returns a generated `session_id` immediately

Success data:

```json
{
  "session_id": "2ac2d8b7-7d88-4c1c-a6ab-2f2a4ecf97e6",
  "device_id": 0,
  "sample_rate": 48000,
  "state": "recording",
  "mode": "rolling",
  "duration_seconds": 5
}
```

Common contract failures:

- `invalid_argument` if `duration_seconds` is missing, not an integer, less than 1, greater than 30, `device_id` is negative, or `sample_rate` is not a positive integer
- `invalid_state` if a session is already recording
- `runtime_failure` for device open failures and other runtime backend errors

### `poll_transcription`

Arguments:

- `session_id: str`

Behavior:

- validates that the requested session matches the active recording session
- stops future rolling capture immediately
- discards any in-progress window
- returns the latest completed transcript if one exists
- returns `status: "pending"` with an empty transcript if no capture window completed yet

Success data:

```json
{
  "session_id": "2ac2d8b7-7d88-4c1c-a6ab-2f2a4ecf97e6",
  "status": "ready",
  "transcript": "hello from whisper",
  "state": "idle",
  "duration_seconds": 5,
  "completed_windows": 2,
  "transcript_updated_at": "2026-07-01T12:00:00Z"
}
```

Pending success data:

```json
{
  "session_id": "2ac2d8b7-7d88-4c1c-a6ab-2f2a4ecf97e6",
  "status": "pending",
  "transcript": "",
  "state": "idle",
  "duration_seconds": 5,
  "completed_windows": 0,
  "transcript_updated_at": null
}
```

Common contract failures:

- `invalid_argument` if `session_id` is empty
- `no_active_session` if nothing is currently recording
- `session_mismatch` if the provided session id does not match the active one
- `invalid_state` if the server is not currently in the `recording` state
- `runtime_failure` if stopping or rolling transcription cleanup fails

### `stop_listening`

Arguments:

- `session_id: str`

Behavior:

- deprecated compatibility alias for `poll_transcription(session_id)`
- stops the same rolling session through the same code path
- returns the same core payload plus deprecation metadata

Success data:

```json
{
  "session_id": "2ac2d8b7-7d88-4c1c-a6ab-2f2a4ecf97e6",
  "status": "ready",
  "transcript": "hello from whisper",
  "state": "idle",
  "duration_seconds": 5,
  "completed_windows": 2,
  "transcript_updated_at": "2026-07-01T12:00:00Z",
  "deprecated": true,
  "replacement": "poll_transcription"
}
```

### `speak_text`

Arguments:

- `text: str`, required, non-empty after trimming, maximum 1000 characters

Behavior:

- speaks text locally on Linux through `espeak-ng`
- uses no cloud text to speech backend

Success data:

```json
{
  "spoken": true,
  "backend": "espeak-ng",
  "characters": 11
}
```

Common contract failures:

- `invalid_argument` if `text` is empty after trimming or longer than 1000 characters
- `runtime_failure` if `espeak-ng` is missing or the local command fails

### `get_server_status`

Arguments: none

Success data:

```json
{
  "state": "idle",
  "active_session_id": null
}
```

`state` is one of `idle` or `recording` for the rolling public flow.

## Practical usage flow

1. Call `list_microphone_devices` to inspect available inputs.
2. Call `start_listening(duration_seconds=5)` with an optional `device_id` and optional `sample_rate`.
3. Let the user speak while the server keeps capturing rolling 5 second windows.
4. Call `poll_transcription(session_id)` when you want to stop and collect the latest completed window.
5. If `data.status` is `pending`, no full window completed before stop.
6. If you need backward compatibility, `stop_listening(session_id)` returns the same core result with deprecation metadata.
7. Call `speak_text(text)` to play local speech through `espeak-ng`.

## Development

Create a local development environment:

```bash
uv sync --locked --all-extras --dev
```

Run the project from the checkout:

```bash
uv run speaktome-mcp
```

Check the module entrypoint from the checkout:

```bash
uv run python -m speaktome_mcp --help
```

## Testing

Run the test suite with:

```bash
uv run pytest -q
```

## Privacy and data handling

- microphone audio is captured locally on the Linux machine running the server
- transcription is performed locally with `faster-whisper`
- text to speech is performed locally with `espeak-ng`
- the project does not use a cloud transcription API
- the project does not use a cloud text to speech API
- audio for the active session is buffered in memory only while that session is running
- only the latest completed transcript window is retained in memory while a rolling session is active
- the current implementation does not intentionally persist active-session audio or transcripts to disk
- first-run model preparation or download may contact model distribution infrastructure so the required model assets can be cached locally

You should still treat the machine, the MCP host, and any host-side logs as part of your privacy boundary. A host application may log tool calls or transcript results even though this server itself keeps only in-memory active-session buffers.

## Troubleshooting

### No microphone device available

Symptoms:

- `list_microphone_devices` returns an empty `devices` list
- `start_listening` fails because no usable input device is available

What to check:

- confirm the microphone is connected and recognized by Linux
- confirm the device is exposed to the same user session that launches the MCP host
- confirm your Linux audio stack is installed and running

### PortAudio or audio backend problems

Symptoms:

- device listing fails
- recording start fails with a `runtime_failure`
- the underlying error mentions PortAudio, ALSA, PipeWire, or device open failures

What to check:

- install the PortAudio packages used by your distro
- confirm ALSA or PipeWire is available in the same user session that launches the MCP host
- if the MCP host runs inside a container, VM, or sandbox, confirm the microphone device is actually passed through

### Microphone permission denied

Symptoms:

- device listing or recording start fails with a `runtime_failure`
- the underlying reason mentions permission denial

What to check:

- allow microphone access in your desktop or sandbox environment if one is in use
- retry from the same Linux user session that can normally access the microphone

### Model startup or load failure

Symptoms:

- the server process exits during startup instead of staying available to the host
- startup errors mention the faster-whisper model failing to load

What to check:

- run your install command again to confirm the Python environment is complete
- make sure the machine can complete the first-run model preparation step
- if the model is not already cached, confirm temporary network access is available so model assets can be fetched
- retry after confirming the local Python environment can import `faster_whisper`

Because the model is loaded eagerly, these failures happen before the first recording starts.

### `espeak-ng` missing or speech playback fails

Symptoms:

- `speak_text` fails with `runtime_failure`
- the underlying reason mentions `espeak-ng` not being found or exiting with an error

What to check:

- install `espeak-ng` with your distro package manager
- confirm `espeak-ng` is on `PATH` for the same Linux user session that launches the MCP host
- try `espeak-ng --version` in that same environment to confirm the binary is available

## Release and download options

You can use this project in several public distribution forms:

- install the published package with `pip install speaktome-mcp`
- install directly from GitHub with `pip install git+https://github.com/alma3lol/SpeakToMeMCP.git`
- download the repository source or a GitHub release source archive, unpack it, then run `pip install .`

If you want to inspect a tagged release before installing, check the GitHub Releases page for source archives and packaged artifacts.
