"""Unit tests for the headless LaunchAgent plist / lifecycle helpers."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from menubar import launch_agent


def test_build_plist_uses_absolute_arguments_run_at_load_and_data_dir_logs():
    plist = launch_agent.build_plist(
        ["/abs/python", "/abs/app.py", "--data-dir", "/data"],
        data_dir="/data",
        env={"TOKENTELEMETRY_CLI": "/abs/cli.js"},
    )

    assert plist["Label"] == "com.tokentelemetry.menubar"
    assert plist["ProgramArguments"] == ["/abs/python", "/abs/app.py", "--data-dir", "/data"]
    assert plist["RunAtLoad"] is True
    assert plist["StandardOutPath"] == "/data/logs/menubar.out.log"
    assert plist["StandardErrorPath"] == "/data/logs/menubar.err.log"
    assert plist["EnvironmentVariables"] == {"TOKENTELEMETRY_CLI": "/abs/cli.js"}


def test_render_plist_round_trips_through_plistlib():
    plist = launch_agent.build_plist(["python", "app.py"], data_dir="/data")
    parsed = plistlib.loads(launch_agent.render_plist(plist))
    assert parsed["Label"] == "com.tokentelemetry.menubar"
    assert parsed["ProgramArguments"] == ["python", "app.py"]
    assert parsed["RunAtLoad"] is True


def test_write_and_remove_plist_under_home(tmp_path):
    home = tmp_path / "home"
    path = launch_agent.write_plist(["python", "app.py"], data_dir="/data", home=home)

    assert path == home / "Library" / "LaunchAgents" / "com.tokentelemetry.menubar.plist"
    assert launch_agent.is_installed(home=home)
    assert path.exists()

    launch_agent.remove_plist(home=home)
    assert not launch_agent.is_installed(home=home)


def test_command_generation_uses_an_explicit_uid():
    assert launch_agent.bootstrap_command("/path/to.plist", uid=501) == [
        "launchctl", "bootstrap", "gui/501", "/path/to.plist",
    ]
    assert launch_agent.bootout_command(uid=501) == [
        "launchctl", "bootout", "gui/501/com.tokentelemetry.menubar",
    ]
    assert launch_agent.print_command(uid=501) == [
        "launchctl", "print", "gui/501/com.tokentelemetry.menubar",
    ]


def test_enable_writes_plist_then_bootstraps(tmp_path):
    calls = []

    def fake_run(command, check=False):
        calls.append((list(command), check))
        return SimpleNamespace(returncode=0)

    home = tmp_path / "home"
    path = launch_agent.enable(
        ["/abs/python", "/abs/app.py"],
        data_dir="/data",
        env={"TOKENTELEMETRY_CLI": "/abs/cli.js"},
        home=home,
        uid=501,
        run=fake_run,
    )

    assert path == launch_agent.plist_path(home=home)
    assert path.exists()
    assert len(calls) == 1
    command, check = calls[0]
    assert command == ["launchctl", "bootstrap", "gui/501", str(path)]
    assert check is True


def test_disable_boots_out_then_removes_plist(tmp_path):
    calls = []

    def fake_run(command, check=False):
        calls.append((list(command), check))
        return SimpleNamespace(returncode=0)

    home = tmp_path / "home"
    launch_agent.write_plist(["python", "app.py"], data_dir="/data", home=home)
    assert launch_agent.is_installed(home=home)

    launch_agent.disable(home=home, uid=501, run=fake_run)

    assert calls == [(["launchctl", "bootout", "gui/501/com.tokentelemetry.menubar"], False)]
    assert not launch_agent.is_installed(home=home)
