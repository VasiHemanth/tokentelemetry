"""Classify raw stderr from summarizer backends into user-friendly cards.

Pure stdlib — keeps the module trivially testable. The classifier returns a
dict shaped for the frontend: a short title, plain-English message, optional
actionable hint, and the truncated raw stderr so the user can still inspect
the underlying error when reporting bugs.
"""

from __future__ import annotations

import json
from typing import Optional

_MAX_RAW = 3000


def _truncate(text: str, limit: int = _MAX_RAW) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… (truncated)"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return text.strip()


def _provider_message(raw: str) -> str:
    """Best-effort: pull a human sentence out of a provider's JSON error body.

    Backend HTTP errors arrive as e.g. ``HTTP 500 from …: {"error":{"message":
    "…"}}``. We parse the embedded JSON and return its ``error.message`` (or
    ``message`` / ``detail``) so the UI can show a sentence instead of a brace
    soup. Returns "" when there's no usable JSON message."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return ""
    try:
        doc = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return ""
    node = doc.get("error", doc) if isinstance(doc, dict) else doc
    if isinstance(node, dict):
        for key in ("message", "detail", "error"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    elif isinstance(node, str) and node.strip():
        return node.strip()
    return ""


def _humanize(raw: str) -> str:
    """A presentable one-line message for an otherwise-unclassified error —
    never a JSON blob. Prefers a provider's JSON message, then a clean first
    line, else a generic fallback (the full text stays in ``raw``)."""
    msg = _provider_message(raw)
    if msg:
        return msg[:300]
    first = _first_line(raw)
    if first and not first.lstrip().startswith(("{", "[")) and len(first) <= 200:
        return first
    return "The summarizer returned an unexpected error. See the raw details below."


# (substring, category) — checked in order, first match wins. "too_large" is
# listed before "quota" because token-budget 413s (Groq's per-minute TPM cap,
# context-length overflows) often *also* carry rate-limit wording, but the
# actionable advice is "shrink the request / bigger model", not "wait".
_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("401", "unauthorized", "invalid_api_key", "incorrect api key"), "auth"),
    (("413", "too large", "request too large", "request_too_large",
      "maximum context", "context length", "context_length_exceeded",
      "reduce your message", "tokens per minute", "too many tokens",
      "input is too long", "prompt is too long"), "too_large"),
    (("429", "rate limit", "rate_limit_exceeded", "quota",
      "exceeded your current quota"), "quota"),
    (("model_not_found", "does not exist", "model not found", "no such model"), "model"),
    (("timed out", "timeout"), "timeout"),
    (("connection refused", "could not connect", "network", "dns"), "network"),
    (("no output", "produced no output", "returned no result text"), "no_output"),
]


def _auth_hint(backend_name: str) -> str:
    b = (backend_name or "").lower()
    if b == "codex":
        return "Run `codex login` (Pro/Plus) or `export OPENAI_API_KEY=sk-...` (API key)."
    if b == "claude":
        return "Run `claude login` or set `ANTHROPIC_API_KEY`."
    if b == "gemini":
        return "Run `gemini auth` or set `GEMINI_API_KEY`."
    if b == "qwen":
        return "Run `qwen auth` or set `DASHSCOPE_API_KEY`."
    if b == "antigravity":
        return "Re-authenticate the Antigravity agent (check `agy auth status`)."
    if b == "openai_compat":
        return "Set the API key in Settings → Summarizer, or via OPENAI_COMPAT_API_KEY."
    return "Check the CLI's auth configuration."


def _network_hint(backend_name: str) -> str:
    b = (backend_name or "").lower()
    if b == "ollama":
        return "Is `ollama serve` running?"
    if b == "openai_compat":
        return "Is your server running and is the endpoint URL correct (e.g. http://localhost:8080/v1)?"
    return "Check your internet connection."


def _timeout_hint(backend_name: str) -> str:
    suffix = (backend_name or "BACKEND").upper() or "BACKEND"
    return f"Try a faster/smaller model, or override the timeout via TT_{suffix}_TIMEOUT."


def _too_large_hint(backend_name: str) -> str:
    if (backend_name or "").lower() == "openai_compat":
        return (
            "This trace is bigger than the model/tier allows. Pick a model with a "
            "larger context window or higher rate-limit tier, switch to a local "
            "backend (Ollama, llama.cpp) with no per-minute cap, or upgrade the "
            "provider plan."
        )
    return "Use a model with a larger context window, or summarize a shorter session."


def classify(stderr_text: str, *, backend_name: str = "") -> dict:
    """Return a structured error card for the given stderr from a summarizer."""
    raw = stderr_text or ""
    raw_trunc = _truncate(raw)
    haystack = raw.lower()

    category = "unknown"
    for needles, cat in _PATTERNS:
        if any(n in haystack for n in needles):
            category = cat
            break

    title: str
    message: str
    hint: Optional[str]

    if category == "auth":
        title = "API key invalid"
        message = "The summarizer CLI rejected your credentials (HTTP 401 / invalid key)."
        hint = _auth_hint(backend_name)
    elif category == "too_large":
        title = "Trace too large for this model"
        message = "The request exceeded the model's context window or the provider's per-minute token budget."
        hint = _too_large_hint(backend_name)
    elif category == "quota":
        title = "Rate limit or quota exceeded"
        message = "The model provider throttled the request or your quota is exhausted."
        hint = "Wait and retry, or pick a cheaper model in Settings → Summarizer."
    elif category == "model":
        title = "Model not available"
        message = "The selected model isn't accessible to your account or the CLI."
        hint = "Pick a different model in Settings → Summarizer that your account can access."
    elif category == "timeout":
        title = "Summarizer timed out"
        message = "The backend didn't return a result before the timeout elapsed."
        hint = _timeout_hint(backend_name)
    elif category == "network":
        title = "Network error"
        message = "The summarizer couldn't reach its backend."
        hint = _network_hint(backend_name)
    elif category == "no_output":
        title = "Empty response"
        message = "The backend completed but returned no narrative text."
        hint = "The backend completed but returned nothing — try a different model or regenerate."
    else:
        title = "Summarizer failed"
        message = _humanize(raw) or "Unknown error."
        hint = None

    return {
        "category": category,
        "title": title,
        "message": message,
        "hint": hint,
        "raw": raw_trunc,
    }
