"""Kimi Code summarizer adapter.

``kimi -p <prompt>`` runs one prompt non-interactively and prints the response
as plain text (its only structured option, ``--output-format stream-json``, is
a verbose event stream, so the default text output is the clean channel). The
CLI appends a ``To resume this session: ...`` trailer line, which is stripped.

Kimi has no stdin prompt mode (``-p`` requires the prompt as an argument), so
the prompt goes via argv — same trade-off the other adapters document: fine on
macOS/Linux ARG_MAX, and trace briefs stay well under it.

Kimi logs its own session under ~/.kimi; running from SUMMARIZER_CWD lets the
ingest layer recognise and skip those phantom traces.
"""
from __future__ import annotations

from .base import BaseSummarizer, SummarizerError, run_cli, _ensure_cwd

_RESUME_TRAILER = "To resume this session:"


class KimiSummarizer(BaseSummarizer):
    name = "kimi"
    display_name = "Kimi Code"
    binary = "kimi"

    def summarize(self, prompt: str, *, timeout: int = 120) -> str:
        out = run_cli(
            [self.binary, "-p", prompt],
            cwd=_ensure_cwd(),
            timeout=timeout,
        )
        text = "\n".join(
            line for line in out.splitlines()
            if not line.startswith(_RESUME_TRAILER)
        ).strip()
        if not text:
            raise SummarizerError("kimi returned no result text")
        return text
