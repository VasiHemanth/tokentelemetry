"""OpenAI-compatible HTTP summarizer adapter.

Unlike every other backend, this one shells out to *nothing*. It POSTs the
prompt to any server that speaks the OpenAI ``/v1/chat/completions`` API —
llama.cpp, vLLM, LM Studio, LocalAI, Ollama's OpenAI endpoint, or a hosted
gateway — and reads the reply back. That lets users reuse a model server they
already run without installing yet another CLI (the ask in discussion #38).

Design notes:
  * Pure stdlib (``urllib``): no new runtime dependency, keeping the
    "no signup, no key, 100 % local-first" promise intact.
  * Synchronous, matching ``BaseSummarizer.summarize`` — the dispatcher calls
    it without ``await``.
  * Error messages embed the HTTP status / failure mode verbatim so
    ``errors.classify`` can bucket them (401 → auth, 429 → quota, connection
    refused → network, timed out → timeout, empty → no_output).
  * An optional bearer token is supported (some local servers and all hosted
    gateways require one). ``OPENAI_COMPAT_API_KEY`` overrides the stored value
    so secrets need not live in ``summarizer.json``.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .base import BaseSummarizer, SummarizerError

_DEFAULT_ENDPOINT = "http://localhost:8080/v1"
# Local inference can be slow; override via env for heavy models / cold loads.
_DEFAULT_TIMEOUT = int(os.environ.get("TT_OPENAI_COMPAT_TIMEOUT", "120"))

# stdlib urllib otherwise sends "User-Agent: Python-urllib/3.x". Cloudflare —
# which fronts hosted gateways like Groq / OpenRouter — keeps a denylist of known
# automation signatures (Python-urllib, python-requests, curl, Go-http-client…)
# and blocks them with Error 1010 before the request reaches the model. An
# honest product UA is not on that denylist, so it passes — exactly how the
# official `openai` SDK's "OpenAI/Python x.y.z" UA gets through. We deliberately
# do NOT impersonate a browser or hard-code an OS string: this ships to Windows,
# macOS, and Linux users, and a faked "Macintosh … Chrome/124" UA would be both
# dishonest and quick to rot. Override via OPENAI_COMPAT_USER_AGENT if a specific
# gateway demands a different signature.
_DEFAULT_USER_AGENT = os.environ.get(
    "OPENAI_COMPAT_USER_AGENT",
    "TokenTelemetry/1.0 (+https://github.com/VasiHemanth/tokentelemetry)",
)

# Reasoning models may prepend a <think>…</think> block; strip it so the
# downstream JSON parse sees the answer, not the chain-of-thought.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class _BadRequest(Exception):
    """Internal: the server answered HTTP 400. Used to trigger a one-shot retry
    with a clean OpenAI-only payload (strict gateways reject non-OpenAI extras
    like top_k / chat_template_kwargs). Never escapes the module."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def default_config() -> Dict[str, Any]:
    """Canonical defaults for the ``openai_compat`` sub-config.

    Mirrored by the schema in discussion #38. Kept here so the backend has a
    single source of truth that ``summaries.save_config`` coerces against.
    """
    return {
        "endpoint": _DEFAULT_ENDPOINT,
        "api_key": "",
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repetition_penalty": 1.0,
        "enable_thinking": False,
    }


class OpenAICompatSummarizer(BaseSummarizer):
    name = "openai_compat"
    display_name = "OpenAI-compatible server"
    binary = ""  # HTTP, not a CLI — see is_available().

    def __init__(
        self,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        cfg = {**default_config(), **(config or {})}
        # Model id is carried at the top level of summarizer.json (reusing the
        # existing per-backend model plumbing), but accept it from the sub-cfg
        # too for the standalone test endpoint.
        self._model = model or cfg.get("model")
        self.endpoint = str(cfg.get("endpoint") or _DEFAULT_ENDPOINT).rstrip("/")
        # SSRF guard: only allow http(s) endpoints. Blocks file://, gopher://,
        # data:// etc. that could turn the "test connection" probe into a
        # local-file read or scheme-exfil vector. The remote-auth gate already
        # keeps unauthenticated callers out; this hardens the value itself.
        _scheme = self.endpoint.split("://", 1)[0].lower() if "://" in self.endpoint else ""
        if _scheme not in ("http", "https"):
            raise SummarizerError(
                f"openai_compat endpoint must be an http(s) URL, got {self.endpoint!r}"
            )
        # Env wins so a key needn't be persisted to disk.
        self.api_key = os.environ.get("OPENAI_COMPAT_API_KEY") or cfg.get("api_key") or ""
        self.max_tokens = int(cfg.get("max_tokens", 512))
        self.temperature = float(cfg.get("temperature", 0.7))
        self.top_p = float(cfg.get("top_p", 0.95))
        self.top_k = int(cfg.get("top_k", 20))
        self.min_p = float(cfg.get("min_p", 0.0))
        self.presence_penalty = float(cfg.get("presence_penalty", 1.5))
        self.repetition_penalty = float(cfg.get("repetition_penalty", 1.0))
        self.enable_thinking = bool(cfg.get("enable_thinking", False))

    def is_available(self) -> bool:
        # No CLI to probe — it's always "installable", so it always shows in the
        # picker as the universal fallback. Whether the configured endpoint is
        # actually reachable surfaces at summarize() time as a network error.
        return True

    def _payload(self, prompt: str, *, include_extensions: bool) -> Dict[str, Any]:
        # Standard OpenAI chat-completions fields — accepted by every compliant
        # server, including strict gateways (Groq, OpenAI itself).
        body: Dict[str, Any] = {
            "model": self._model or "default",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "stream": False,
        }
        if include_extensions:
            # Non-OpenAI sampling knobs. llama.cpp / vLLM read these at the top
            # level and honour them; strict gateways reject unknown properties
            # with HTTP 400, which triggers the clean-payload retry in
            # summarize(). top_k / min_p / repetition_penalty come from
            # discussion #38's schema.
            body["top_k"] = self.top_k
            body["min_p"] = self.min_p
            body["repetition_penalty"] = self.repetition_penalty
            # Only emit the reasoning toggle when the user actually turned it on:
            # it's meaningful to Qwen3 / vLLM and rejected outright elsewhere.
            if self.enable_thinking:
                body["chat_template_kwargs"] = {"enable_thinking": True}
        return body

    def summarize(self, prompt: str, *, timeout: Optional[int] = None) -> str:
        tmo = timeout if timeout is not None else _DEFAULT_TIMEOUT
        url = f"{self.endpoint}/chat/completions"
        # Try the full payload (with non-OpenAI extras) first. If a strict server
        # rejects an unknown property with 400, retry once with an OpenAI-only
        # payload so the summary still goes through — the extras it couldn't
        # honour are simply dropped.
        try:
            raw = self._post(url, self._payload(prompt, include_extensions=True), tmo)
        except _BadRequest:
            try:
                raw = self._post(url, self._payload(prompt, include_extensions=False), tmo)
            except _BadRequest as e:
                raise SummarizerError(f"HTTP 400 from {url}: {e.detail}") from e
        return _extract_text(raw, url)

    def _post(self, url: str, payload: Dict[str, Any], tmo: int) -> str:
        """POST one payload. Returns raw body, raises ``_BadRequest`` on HTTP 400
        (retryable), or ``SummarizerError`` on any other failure."""
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=tmo) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code == 400:
                raise _BadRequest(detail or str(e.reason)) from e
            # Keep the numeric status in the message so classify() can bucket it.
            raise SummarizerError(f"HTTP {e.code} from {url}: {detail or e.reason}") from e
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise SummarizerError(f"request to {url} timed out after {tmo}s") from e
            raise SummarizerError(
                f"could not connect to {url}: connection refused — {reason}"
            ) from e
        except (TimeoutError, OSError) as e:
            raise SummarizerError(f"request to {url} timed out after {tmo}s: {e}") from e


def _coerce_content(content: Any) -> str:
    """Reduce a message ``content`` to text. Most servers return a string; some
    (vision-style) return a list of typed parts — join the textual ones."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") in (None, "text")
        ]
        return "".join(parts)
    return ""


def _extract_text(raw: str, url: str) -> str:
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SummarizerError(f"non-JSON response from {url}: {raw[:300]}") from e

    choices = doc.get("choices") or []
    if choices:
        first = choices[0] or {}
        message = first.get("message") or {}
        content = _coerce_content(message.get("content"))
        if not content:
            # Completions-style fallback (some servers fill .text not .message).
            content = _coerce_content(first.get("text"))
        content = _THINK_RE.sub("", content).strip()
        if content:
            return content

    # Surface an upstream error object if the server returned one.
    err = doc.get("error")
    if err:
        emsg = err.get("message") if isinstance(err, dict) else str(err)
        raise SummarizerError(f"server error: {emsg}")

    raise SummarizerError(f"{url} produced no output")
