import subprocess
import sys

import pytest


def run_help_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    [
        (sys.executable, "-m", "speaktome_mcp.server"),
        (sys.executable, "-m", "speaktome_mcp"),
        ("speaktome-mcp",),
    ],
)
def test_help_entrypoints_exit_zero(
    command: tuple[str, ...],
) -> None:
    result = run_help_command(*command)

    assert result.returncode == 0
    assert "SpeakToMe MCP server over stdio" in result.stdout
    assert "usage:" in result.stdout
    assert "--transport {stdio}" in result.stdout
    assert "--help" in result.stdout
