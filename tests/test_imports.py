import subprocess
import sys

from speaktome_mcp import __version__
from speaktome_mcp.server import SERVER_NAME, build_parser, build_server


def test_package_imports() -> None:
    assert __version__ == "0.1.0"
    assert SERVER_NAME == "speaktome-mcp"


def test_package_import_in_subprocess_is_side_effect_free() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import speaktome_mcp; import speaktome_mcp.server; print(speaktome_mcp.__version__)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == __version__
    assert result.stderr == ""


def test_server_factory_creates_named_server() -> None:
    server = build_server()
    assert server.name == SERVER_NAME


def test_parser_defaults_to_stdio() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.transport == "stdio"
