from __future__ import annotations

from pathlib import Path

import anyio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = """
from speaktome_mcp.server import build_server
from speaktome_mcp.tools import SpeakToMeToolHandlers
from tests.fakes import FakeAudioCapture, FakeSessionManager, make_audio_input_device


def build_handlers():
    session_manager = FakeSessionManager(
        start_result={
            'ok': True,
            'tool': 'start_listening',
            'data': {
                'session_id': 'session-123',
                'device_id': 1,
                'sample_rate': 16000,
                'state': 'recording',
            },
        },
        stop_result={
            'ok': True,
            'tool': 'stop_listening',
            'data': {
                'session_id': 'session-123',
                'transcript': '',
                'state': 'idle',
            },
        },
        status_result={
            'ok': True,
            'tool': 'get_server_status',
            'data': {
                'state': 'idle',
                'active_session_id': None,
            },
        },
    )
    return SpeakToMeToolHandlers(
        audio_capture=FakeAudioCapture(devices=[make_audio_input_device()]),
        session_manager=session_manager,
    )


build_server(handler_factory=build_handlers, eager=True).run(transport='stdio')
""".strip()


def test_stdio_server_exposes_expected_tool_surface() -> None:
    async def exercise_stdio_server() -> None:
        params = StdioServerParameters(
            command="uv",
            args=["run", "python", "-c", SERVER_SCRIPT],
            cwd=str(REPO_ROOT),
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tool_names = [tool.name for tool in tools_result.tools]

                assert tool_names == [
                    "list_microphone_devices",
                    "start_listening",
                    "stop_listening",
                    "get_server_status",
                ]

                status_result = await session.call_tool("get_server_status", {})

                assert status_result.isError is False
                assert status_result.structuredContent == {
                    "ok": True,
                    "tool": "get_server_status",
                    "data": {
                        "state": "idle",
                        "active_session_id": None,
                    },
                }

                list_result = await session.call_tool("list_microphone_devices", {})
                assert list_result.isError is False
                assert list_result.structuredContent == {
                    "ok": True,
                    "tool": "list_microphone_devices",
                    "data": {
                        "devices": [
                            {
                                "id": 1,
                                "name": "Fake Mic",
                                "max_input_channels": 1,
                                "default_sample_rate": 16000,
                                "is_default": True,
                            }
                        ]
                    },
                }

                start_result = await session.call_tool("start_listening", {"device_id": 1})
                assert start_result.isError is False
                assert start_result.structuredContent == {
                    "ok": True,
                    "tool": "start_listening",
                    "data": {
                        "session_id": "session-123",
                        "device_id": 1,
                        "sample_rate": 16000,
                        "state": "recording",
                    },
                }

                stop_result = await session.call_tool("stop_listening", {"session_id": "session-123"})
                assert stop_result.isError is False
                assert stop_result.structuredContent == {
                    "ok": True,
                    "tool": "stop_listening",
                    "data": {
                        "session_id": "session-123",
                        "transcript": "",
                        "state": "idle",
                    },
                }

    anyio.run(exercise_stdio_server)
