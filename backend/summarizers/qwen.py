"""Qwen Code summarizer adapter.

``qwen <prompt> -o json`` runs headlessly (positional prompt; ``-p`` is
deprecated). It prints a JSON array of event objects; the final ``result`` event
carries the model's text and a success/error subtype:
  [..., {"type":"result","subtype":"success","result":"<text>",...}]
On failure the result event has ``is_error`` and an ``error.message``.

Qwen logs its own session; running from SUMMARIZER_CWD lets the ingest layer
recognise and skip those phantom traces.
"""
from __future__ import annotations

import json

from .base import BaseSummarizer, SummarizerError, run_cli, _ensure_cwd


class QwenSummarizer(BaseSummarizer):
    name = "qwen"
    display_name = "Qwen Code"
    binary = "qwen"

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
        # The envelope is a list of events; pull the terminal ``result`` event.
        events = data if isinstance(data, list) else [data]
        result_event = next(
            (e for e in events if isinstance(e, dict) and e.get("type") == "result"),
            None,
        )
        if result_event is None:
            raise SummarizerError("qwen returned no result event")
        if result_event.get("is_error"):
            msg = (result_event.get("error") or {}).get("message") or "unknown error"
            raise SummarizerError(f"qwen error: {msg}")
        result = result_event.get("result")
        if not result:
            raise SummarizerError("qwen returned no result text")
        return str(result)
