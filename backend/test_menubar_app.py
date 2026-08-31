"""Unit tests for the headless menubar platform / argument helpers.

These import ``menubar.app`` but never ``rumps``: the app module imports rumps
only inside ``run()`` after the platform guard, so this file proves the module
is importable (and its helpers callable) without touching Cocoa or PyObjC.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from menubar import app


def test_is_macos_matches_the_running_platform():
    assert app.is_macos() == (sys.platform == "darwin")


def test_parse_args_reads_and_defaults_data_dir():
    assert app.parse_args([]).data_dir is None
    assert app.parse_args(["--data-dir", "/tmp/tt-data"]).data_dir == "/tmp/tt-data"


def test_configure_environment_sets_the_data_dir_env_var():
    args = app.parse_args(["--data-dir", "/tmp/tt-data"])
    previous = os.environ.get("TOKENTELEMETRY_DATA_DIR")
    try:
        app.configure_environment(args)
        assert os.environ["TOKENTELEMETRY_DATA_DIR"] == os.path.abspath("/tmp/tt-data")
    finally:
        if previous is None:
            os.environ.pop("TOKENTELEMETRY_DATA_DIR", None)
        else:
            os.environ["TOKENTELEMETRY_DATA_DIR"] = previous


def test_program_arguments_are_absolute_and_forward_data_dir():
    argv = app.program_arguments(
        python="/abs/python",
        app_path="/abs/menubar/app.py",
        data_dir="/data",
    )
    assert argv == ["/abs/python", "/abs/menubar/app.py", "--data-dir", "/data"]

    argv = app.program_arguments(python="/abs/python", app_path="/abs/menubar/app.py")
    assert argv == ["/abs/python", "/abs/menubar/app.py"]

    # Defaults are absolute: sys.executable and this file.
    default = app.program_arguments()
    assert default[0] == sys.executable
    assert Path(default[1]).is_absolute()


def test_resolve_dashboard_command_prefers_environment_then_which():
    env = {"TOKENTELEMETRY_NODE": "/abs/node", "TOKENTELEMETRY_CLI": "/abs/cli.js"}
    assert app.resolve_dashboard_command(env=env) == ["/abs/node", "/abs/cli.js", "dashboard"]

    # Missing CLI path yields None even if node is available.
    assert app.resolve_dashboard_command(env={"TOKENTELEMETRY_NODE": "/abs/node"}) is None

    # Falls back to `node` on PATH when TOKENTELEMETRY_NODE is absent.
    def fake_which(cmd):
        return "/usr/bin/node" if cmd == "node" else None

    assert app.resolve_dashboard_command(
        env={"TOKENTELEMETRY_CLI": "/abs/cli.js"},
        which=fake_which,
    ) == ["/usr/bin/node", "/abs/cli.js", "dashboard"]


def test_program_arguments_defaults_to_absolute_sys_executable_and_file():
    argv = app.program_arguments()
    assert argv[0] == sys.executable
    assert Path(argv[1]).is_absolute()
