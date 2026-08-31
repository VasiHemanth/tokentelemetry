"""macOS menu bar app: a thin ``rumps`` adapter over ``menubar.presentation``.

The split that matters for testing lives in this module's imports: ``rumps`` is
imported only inside :func:`run`, after an explicit macOS platform guard, so
importing this module (and unit-testing its argument / platform helpers) never
touches Cocoa or PyObjC. All quota wording and the single worst-window choice
come from :mod:`menubar.presentation`, which has no macOS dependency either.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Union

# Make the `menubar` package (and its siblings quotas / tt_paths) importable no
# matter how this file is launched: by the CLI (cwd=backend, PYTHONPATH=backend),
# by a LaunchAgent (which sets no PYTHONPATH), or directly as a script. Python
# otherwise puts this file's own directory on sys.path, not the repo backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from menubar import launch_agent, render
from menubar.presentation import MenuBarPresentation, build_menu_presentation

APP_NAME = "TokenTelemetry"
REFRESH_SECONDS = 60.0

# Headless placeholder for the moment between launch and the first collect.
_LOADING = build_menu_presentation(None, loading=True)


def is_macos() -> bool:
    """Platform guard; the CLI and the runtime both refuse elsewhere."""
    return sys.platform == "darwin"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tokentelemetry menubar",
        description="TokenTelemetry menu bar app (macOS only).",
    )
    parser.add_argument(
        "--data-dir",
        metavar="PATH",
        default=None,
        help="Override the TokenTelemetry data directory (sets TOKENTELEMETRY_DATA_DIR).",
    )
    return parser.parse_args(argv)


def configure_environment(args: argparse.Namespace) -> None:
    """Fold --data-dir into TOKENTELEMETRY_DATA_DIR before tt_paths is read."""
    if args.data_dir:
        os.environ["TOKENTELEMETRY_DATA_DIR"] = os.path.abspath(os.path.expanduser(args.data_dir))


def program_arguments(
    python: Optional[str] = None,
    app_path: Optional[str] = None,
    data_dir: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Absolute program arguments for a LaunchAgent that runs this app."""
    argv = [python or sys.executable, app_path or os.path.abspath(__file__)]
    if data_dir:
        argv += ["--data-dir", str(data_dir)]
    return argv


def resolve_dashboard_command(
    env: Optional[Mapping[str, str]] = None,
    which: Any = None,
) -> Optional[List[str]]:
    """The command that opens the dashboard via the shared CLI.

    The CLI passes its own absolute path and the Node executable that runs it
    through the environment, so this never hard-codes a checkout or account
    path. Falls back to ``node`` on PATH; returns ``None`` when unavailable.
    """
    env = os.environ if env is None else env
    which = which or shutil.which
    node = env.get("TOKENTELEMETRY_NODE") or which("node")
    cli = env.get("TOKENTELEMETRY_CLI")
    if not node or not cli:
        return None
    return [node, cli, "dashboard"]


def run(argv: Optional[Sequence[str]] = None) -> int:
    if not is_macos():
        print("The tokentelemetry menu bar is macOS-only.", file=sys.stderr)
        return 1

    args = parse_args(argv)
    configure_environment(args)

    import rumps  # noqa: PLC0415 — macOS-only, after the platform guard
    from PyObjCTools import AppHelper
    from quotas import QuotaService, default_quota_providers
    from tt_paths import data_dir

    data = data_dir()

    class MenubarApp(rumps.App):
        def __init__(self, service: Any, data: Path, app_helper: Any) -> None:
            super().__init__(APP_NAME, title=_LOADING.title, quit_button=None)
            self._service = service
            self._data_dir = data
            self._app_helper = app_helper
            self._refresh_lock = threading.Lock()
            self._refreshing = False
            self._refresh_queued = False
            self._presentation = _LOADING
            self._rebuild_menu()
            self._request_refresh(force=False)

        @rumps.timer(REFRESH_SECONDS)
        def _tick(self, _sender: Any) -> None:
            self._request_refresh(force=False)

        def _request_refresh(self, force: bool = False) -> None:
            with self._refresh_lock:
                if self._refreshing:
                    if force:
                        self._refresh_queued = True
                    return
                self._refreshing = True
            threading.Thread(target=self._refresh_worker, args=(force,), daemon=True).start()

        def _refresh_worker(self, force: bool) -> None:
            failure: Optional[str] = None
            try:
                response = self._service.collect(force=force)
            except Exception as error:  # noqa: BLE001 — surface, don't crash the menubar
                response = None
                failure = str(error) or type(error).__name__
            presentation = build_menu_presentation(response, failure=failure)
            self._app_helper.callAfter(lambda p=presentation: self._apply_presentation(p))
            with self._refresh_lock:
                self._refreshing = False
                queued = self._refresh_queued
                self._refresh_queued = False
            if queued:
                self._request_refresh(force=True)

        def _apply_presentation(self, presentation: MenuBarPresentation) -> None:
            self._presentation = presentation
            self.title = presentation.title
            self._rebuild_menu()

        def _rebuild_menu(self) -> None:
            self.menu.clear()
            for item in render.build_rumps_menu(self._presentation, handler=self._on_action):
                self.menu.add(item)

        def _on_action(self, kind: str, _sender: Any) -> None:
            if kind == "open":
                self._on_open_dashboard(_sender)
            elif kind == "refresh":
                self._on_refresh_now(_sender)
            elif kind == "launch":
                self._on_toggle_launch(_sender)

        def _on_open_dashboard(self, _sender: Any) -> None:
            command = resolve_dashboard_command()
            if not command:
                return
            try:
                subprocess.Popen(
                    command,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass

        def _on_refresh_now(self, _sender: Any) -> None:
            self._request_refresh(force=True)

        def _launch_env(self) -> dict:
            env: dict = {}
            for key in ("TOKENTELEMETRY_CLI", "TOKENTELEMETRY_NODE", "TOKENTELEMETRY_DATA_DIR"):
                value = os.environ.get(key)
                if value:
                    env[key] = value
            return env

        def _on_toggle_launch(self, _sender: Any) -> None:
            if launch_agent.is_installed():
                launch_agent.disable()
            else:
                launch_agent.enable(
                    program_args=program_arguments(data_dir=self._data_dir),
                    data_dir=self._data_dir,
                    env=self._launch_env(),
                )
            self._rebuild_menu()

    app = MenubarApp(QuotaService(default_quota_providers()), data, AppHelper)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
