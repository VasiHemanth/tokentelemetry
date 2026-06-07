"""Antigravity CLI summarizer adapter.

Google's Antigravity CLI (the Go-based `agy`, which replaced Gemini CLI in
May 2026) runs a single prompt headlessly with `agy -p`. We pass
`--dangerously-skip-permissions` so unattended runs never block on a tool
permission prompt, and cap it with the binary's own `--print-timeout`.

`agy` shares the Antigravity agent harness and logs its conversation under
~/.gemini/antigravity; running from SUMMARIZER_CWD lets the ingest layer skip
those phantom traces. Output is plain text (no JSON envelope), so we strip ANSI
before handing it on.
"""
from __future__ import annotations

import re

from .base import BaseSummarizer, run_cli, _ensure_cwd

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class AntigravitySummarizer(BaseSummarizer):
    name = "antigravity"
    display_name = "Antigravity"
    binary = "agy"

    def summarize(self, prompt: str, *, timeout: int = 180) -> str:
        out = run_cli(
            [
                self.binary,
                "--dangerously-skip-permissions",
                "--print-timeout", f"{timeout}s",
            ],
            stdin=prompt,
            cwd=_ensure_cwd(),
            # Give the process a little slack past its own print-timeout so the
            # binary's timeout fires first with a cleaner message.
            timeout=timeout + 15,
        )
        return _ANSI_RE.sub("", out).strip()
