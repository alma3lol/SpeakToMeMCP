## Contributing

Thanks for helping improve SpeakToMe MCP.

## Prerequisites

- Linux
- Python 3.11 or newer
- `uv`
- system audio libraries needed by `sounddevice`

## Local setup

```bash
uv sync --locked --all-extras --dev
```

## Run tests

```bash
uv run pytest -q
```

## Build packages

```bash
uv build
```

This creates the source distribution and wheel under `dist/`.

## Validate package metadata

```bash
uv run --with twine twine check --strict dist/*
```

## Before opening a pull request

Run the setup, test, build, and package validation commands above.

Keep changes focused. If you update behavior, docs, packaging, or workflows, include the matching tests or documentation updates in the same pull request.

## Scope notes

This project is Linux-only in v1 and uses stdio transport only. Avoid adding Windows, macOS, HTTP, WebSocket, SSE, or streaming transcript claims unless the implementation changes first.
