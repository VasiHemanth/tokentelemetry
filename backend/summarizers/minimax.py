"""MiniMax HTTP summarizer adapter."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .base import BaseSummarizer, SummarizerError

SUPPORTED_MODELS = ("MiniMax-M3", "MiniMax-M2.7")
DEFAULT_MODEL = SUPPORTED_MODELS[0]

REGIONS = {
    "global_en": {
        "label": "Global",
        "openai": "https://api.minimax.io/v1",
        "anthropic": "https://api.minimax.io/anthropic",
    },
    "cn_zh": {
        "label": "China",
        "openai": "https://api.minimaxi.com/v1",
        "anthropic": "https://api.minimaxi.com/anthropic",
    },
}
PROTOCOLS = {
    "anthropic": "Anthropic-compatible",
    "openai": "OpenAI-compatible",
}
THINKING_MODES = ("adaptive", "disabled")

_DEFAULT_TIMEOUT = int(os.environ.get("TT_MINIMAX_TIMEOUT", "120"))
_USER_AGENT = "TokenTelemetry/1.0"


def default_config() -> Dict[str, Any]:
    return {
        "region": "global_en",
        "protocol": "anthropic",
        "api_key": "",
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.95,
        "thinking": "adaptive",
    }


def coerce_config(raw: Any) -> Dict[str, Any]:
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg

    if raw.get("region") in REGIONS:
        cfg["region"] = raw["region"]
    if raw.get("protocol") in PROTOCOLS:
        cfg["protocol"] = raw["protocol"]
    if raw.get("thinking") in THINKING_MODES:
        cfg["thinking"] = raw["thinking"]
    if raw.get("api_key") is not None:
        cfg["api_key"] = str(raw["api_key"])

    for key, caster in (
        ("max_tokens", int),
        ("temperature", float),
        ("top_p", float),
    ):
        if raw.get(key) is None:
            continue
        try:
            cfg[key] = caster(raw[key])
        except (TypeError, ValueError):
            pass
    return cfg


def available_options() -> Dict[str, Any]:
    return {
        "default_model": DEFAULT_MODEL,
        "models": [{"name": model, "label": model} for model in SUPPORTED_MODELS],
        "regions": [
            {"name": name, "label": values["label"]}
            for name, values in REGIONS.items()
        ],
        "protocols": [
            {"name": name, "label": label}
            for name, label in PROTOCOLS.items()
        ],
    }


class MiniMaxSummarizer(BaseSummarizer):
    name = "minimax"
    display_name = "MiniMax"
    binary = ""

    def __init__(
        self,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        cfg = coerce_config(config)
        self.model = model or DEFAULT_MODEL
        if self.model not in SUPPORTED_MODELS:
            raise SummarizerError(f"unsupported MiniMax model {self.model!r}")
        self.region = cfg["region"]
        self.protocol = cfg["protocol"]
        self.endpoint = REGIONS[self.region][self.protocol]
        self.api_key = os.environ.get("MINIMAX_API_KEY") or cfg["api_key"]
        self.max_tokens = cfg["max_tokens"]
        self.temperature = cfg["temperature"]
        self.top_p = cfg["top_p"]
        self.thinking = cfg["thinking"]

    def is_available(self) -> bool:
        return True

    def summarize(self, prompt: str, *, timeout: Optional[int] = None) -> str:
        tmo = timeout if timeout is not None else _DEFAULT_TIMEOUT
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,
        }
        if self.model == "MiniMax-M3":
            payload["thinking"] = {"type": self.thinking}

        if self.protocol == "anthropic":
            url = f"{self.endpoint}/v1/messages"
            raw = self._post(url, payload, headers, tmo)
            return _extract_anthropic_text(raw, url)

        url = f"{self.endpoint}/chat/completions"
        raw = self._post(url, payload, headers, tmo)
        return _extract_openai_text(raw, url)

    def _post(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        timeout: int,
    ) -> str:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise SummarizerError(
                f"HTTP {e.code} from {url}: {detail or e.reason}"
            ) from e
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise SummarizerError(
                    f"request to {url} timed out after {timeout}s"
                ) from e
            raise SummarizerError(f"could not connect to {url}: {reason}") from e
        except (TimeoutError, OSError) as e:
            raise SummarizerError(
                f"request to {url} timed out after {timeout}s: {e}"
            ) from e


def _decode(raw: str, url: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SummarizerError(f"non-JSON response from {url}: {raw[:300]}") from e


def _extract_openai_text(raw: str, url: str) -> str:
    doc = _decode(raw, url)
    choices = doc.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            )
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise SummarizerError(f"{url} produced no output")


def _extract_anthropic_text(raw: str, url: str) -> str:
    doc = _decode(raw, url)
    content = doc.get("content") or []
    text = "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if text:
        return text
    raise SummarizerError(f"{url} produced no output")
