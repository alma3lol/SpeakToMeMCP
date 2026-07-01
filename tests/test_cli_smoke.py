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
    ("command", "expected_usage_fragment"),
    [
        ((sys.executable, "-m", "speaktome_mcp.server"), "-m speaktome_mcp.server"),
        ((sys.executable, "-m", "speaktome_mcp"), "-m speaktome_mcp"),
        (("speaktome-mcp",), "speaktome-mcp"),
    ],
)
def test_help_entrypoints_exit_zero(
    command: tuple[str, ...],
    expected_usage_fragment: str,
) -> None:
    result = run_help_command(*command)

    assert result.returncode == 0
    assert "SpeakToMe MCP server over stdio" in result.stdout
    assert "usage:" in result.stdout
    assert expected_usage_fragment in result.stdout
