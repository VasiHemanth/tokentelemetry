"""Codex CLI summarizer adapter.

``codex exec`` runs non-interactively. We bypass every approval/sandbox prompt
(``--dangerously-bypass-approvals-and-sandbox``) and allow running outside a git
repo (``--skip-git-repo-check``) so the call is fully headless. The agent's final
message is written to a temp file via ``-o`` so we get clean text without the
banner/event noise that goes to stdout.

The prompt is piped via stdin (positional ``-``). Passing it as argv works for
short traces but hits ARG_MAX / shell-escape problems on long ones — and trace
prompts are routinely >100 KB.

Codex logs its own session under ~/.codex; running from SUMMARIZER_CWD lets the
ingest layer recognise and skip those phantom traces.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from .base import BaseSummarizer, SummarizerError, run_cli, _ensure_cwd


# Codex (gpt-5.x + medium reasoning) on a real trace can comfortably take
# 2-4 minutes; the previous 120s default was a frequent timeout cause.
_DEFAULT_TIMEOUT = int(os.environ.get("TT_CODEX_TIMEOUT", "300"))


# Curated cheaper-tier OpenAI models that work via API key without a Pro/Plus
# subscription. The frontend shows these in the model picker so non-Pro users
# can avoid the (often gated) default. "Auto" passes no --model and lets the
# Codex CLI use whatever's configured in ~/.codex/config.toml.
SUGGESTED_MODELS: list[dict] = [
    {"name": "gpt-5-mini",   "label": "GPT-5 mini",  "hint": "Fast, cheap, good for summaries"},
    {"name": "gpt-5-nano",   "label": "GPT-5 nano",  "hint": "Cheapest GPT-5 tier"},
    {"name": "gpt-4o-mini",  "label": "GPT-4o mini", "hint": "Reliable fallback if GPT-5 isn't on your account"},
    {"name": "o3-mini",      "label": "o3 mini",     "hint": "Reasoning model — slower, deeper"},
    {"name": "gpt-5",        "label": "GPT-5",       "hint": "Requires Pro/Plus or sufficient API tier"},
    {"name": "gpt-5.5",      "label": "GPT-5.5",     "hint": "Requires Pro/Plus or sufficient API tier"},
]


class CodexSummarizer(BaseSummarizer):
    name = "codex"
    display_name = "Codex"
    binary = "codex"

    def __init__(self, model: Optional[str] = None) -> None:
        self._model = model

    def summarize(
        self, prompt: str, *, timeout: Optional[int] = None, untrusted: bool = False
    ) -> str:
        """``untrusted=True`` is for prompts that embed transcript text: codex
        runs in its read-only sandbox instead of with the sandbox bypassed."""
        with tempfile.NamedTemporaryFile(
            "r", suffix=".txt", prefix="tt-codex-", delete=False
        ) as f:
            last_message = f.name
        try:
            args = [
                self.binary,
                "exec",
            ]
            if untrusted:
                args += ["-s", "read-only"]
            else:
                args += ["--dangerously-bypass-approvals-and-sandbox"]
            args += ["--skip-git-repo-check", "-o", last_message]
            # Only override the model when the user explicitly picked one.
            # Otherwise let codex honor ~/.codex/config.toml.
            if self._model:
                args += ["-m", self._model]
            # `-` tells codex to read the prompt from stdin.
            args += ["-"]
            # stdout carries a banner + event log; the clean final message is
            # written to ``last_message`` by ``-o``.
            run_cli(
                args,
                stdin=prompt,
                cwd=_ensure_cwd(),
                timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT,
            )
            text = Path(last_message).read_text().strip()
        finally:
            Path(last_message).unlink(missing_ok=True)
        if not text:
            raise SummarizerError("codex returned no result text")
        return text
