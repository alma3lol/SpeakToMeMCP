"""SpeakToMe MCP stdio server bootstrap."""

from __future__ import annotations

import argparse
from importlib import import_module
from typing import Callable

from mcp.server.fastmcp import FastMCP

from speaktome_mcp.audio import AudioCapture, SoundDeviceAudioCapture
from speaktome_mcp.session import SessionManager
from speaktome_mcp.speech import EspeakSpeechService, SpeechService
from speaktome_mcp.state import ServerStateMachine
from speaktome_mcp.tools import SpeakToMeToolHandlers, register_tools
from speaktome_mcp.transcription import TranscriptionService, load_transcription_service


SERVER_NAME = "speaktome-mcp"
ToolHandlerFactory = Callable[[], SpeakToMeToolHandlers]


def build_default_tool_handlers() -> SpeakToMeToolHandlers:
    """Create the production audio/session tool dependencies."""

    sounddevice_module = import_module("sounddevice")
    audio_capture: AudioCapture = SoundDeviceAudioCapture(sounddevice_module)
    transcription_service: TranscriptionService = load_transcription_service()
    speech_service: SpeechService = EspeakSpeechService()
    session_manager = SessionManager(
        state_machine=ServerStateMachine(),
        audio_capture=audio_capture,
        transcription_service=transcription_service,
    )
    return SpeakToMeToolHandlers(
        audio_capture=audio_capture,
        session_manager=session_manager,
        speech_service=speech_service,
    )


def build_server(
    *,
    handler_factory: ToolHandlerFactory | None = None,
    eager: bool = False,
) -> FastMCP:
    """Create the stdio MCP server with the finalized four-tool surface."""

    resolved_factory = handler_factory or build_default_tool_handlers
    handler_cache: SpeakToMeToolHandlers | None = None

    def get_handlers() -> SpeakToMeToolHandlers:
        nonlocal handler_cache
        if handler_cache is None:
            handler_cache = resolved_factory()
        return handler_cache

    if eager:
        get_handlers()

    server = FastMCP(name=SERVER_NAME)
    register_tools(server, get_handlers)
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the SpeakToMe MCP server over stdio.",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio"],
        help="Transport to run. Only stdio is supported in v1.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    server = build_server(eager=True)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
