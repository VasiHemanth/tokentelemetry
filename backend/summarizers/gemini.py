"""Gemini CLI summarizer adapter.

``gemini -p <prompt> -o json`` runs headlessly and prints a JSON envelope whose
``response`` field holds the model's text:
  {"session_id":"...","response":"<text>","stats":{...}}

Gemini logs its own session for the project; running from SUMMARIZER_CWD lets the
ingest layer recognise and skip those phantom traces.
"""
from __future__ import annotations

import json

from .base import BaseSummarizer, SummarizerError, run_cli, _ensure_cwd


class GeminiSummarizer(BaseSummarizer):
    name = "gemini"
    display_name = "Gemini CLI"
    binary = "gemini"

    def summarize(self, prompt: str, *, timeout: int = 120) -> str:
        out = run_cli(
            [self.binary, "-o", "json"],
            stdin=prompt,
            cwd=_ensure_cwd(),
            timeout=timeout,
        )
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            # Fall back to raw stdout if the CLI ever changes its envelope.
            return out
        response = data.get("response")
        if not response:
            raise SummarizerError("gemini returned no response text")
        return str(response)
