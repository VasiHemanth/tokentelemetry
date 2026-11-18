"""Secret redaction for text that recall returns to a caller.

``redact(text)`` replaces anything that looks like a credential with
``[REDACTED:<kind>]``. Rules run in order: PEM blocks and vendor-specific
prefixes first, the generic key/value rule last, so a specific kind is never
relabelled as ``assignment``.

This is pattern matching, not a guarantee. It targets well-known token shapes
and obvious ``name=value`` assignments. Every pattern is anchored with a
lookbehind or bounded quantifier so a long unbroken run stays linear.

Recall redacts per ~600-char chunk, so a PEM body split across chunks would
reach later chunks without its BEGIN line. ``recall.mask_key_continuations``
covers that case before ``redact`` runs.
"""
from __future__ import annotations

import re
from typing import Any, Callable, List, Tuple, Union

_Repl = Union[str, Callable[[re.Match], str]]


def _tag(kind: str) -> str:
    return f"[REDACTED:{kind}]"


_LITERALS = frozenset({"true", "false", "none", "null", "undefined", "nil"})
# Looks like code rather than a secret: a snake_case identifier (has an
# underscore) or a dotted attribute path. A bare lowercase word such as a
# passphrase does not qualify, so it is still redacted.
_CODE_VALUE = re.compile(r"[a-z_][a-z0-9]*_[a-z0-9_]*|[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+")


def _assignment(m: re.Match) -> str:
    value = m.group(2)
    tail = m.string[m.end():m.end() + 1]
    if (value.startswith("$") or value.isdigit() or value.lower() in _LITERALS
            or _CODE_VALUE.fullmatch(value) or tail == "("):
        return m.group(0)
    return m.group(1) + _tag("assignment")


_RULES: List[Tuple[re.Pattern, _Repl]] = [
    (re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
        r"(?:[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----|[\s\S]*$)"), _tag("private_key")),
    (re.compile(r"-----END [A-Z ]*PRIVATE KEY-----"), _tag("private_key")),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), _tag("aws_access_key")),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})"), _tag("github_token")),
    (re.compile(r"(?<![A-Za-z0-9_])sk-ant-[A-Za-z0-9_\-]{20,}"), _tag("anthropic_key")),
    (re.compile(r"(?<![A-Za-z0-9_])sk-(?:proj-)?(?=[A-Za-z0-9_\-]{0,200}\d)[A-Za-z0-9_\-]{20,}"), _tag("openai_key")),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), _tag("slack_token")),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), _tag("google_api_key")),
    (re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}"), _tag("stripe_key")),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), _tag("jwt")),
    (re.compile(r"(?i)(?:\bAuthorization\s*:\s*)?\bBearer\s+[A-Za-z0-9._~+/=\-]{16,}"), _tag("bearer")),
    (re.compile(r"(?i)(?:\bAuthorization\s*:\s*)?\bBasic\s+[A-Za-z0-9+/]{16,}={0,2}"), _tag("basic_auth")),
    (re.compile(r"(?<![A-Za-z0-9+.\-])([A-Za-z][A-Za-z0-9+.\-]{0,31}://)[^\s/:@]{1,256}:[^\s/@]{1,256}@"),
     lambda m: m.group(1) + _tag("url_credentials") + "@"),
    (re.compile(
        r"(?i)((?<![A-Za-z0-9_.\-])[A-Za-z0-9_.\-]{0,40}(?:password|passwd|secret|api[_\-]?key|apikey|token|credential)s?[A-Za-z0-9_]{0,24}"
        r"[\"']?\s*[:=]\s*[\"']?)([^\s\"'`,;&()\[\]{}<>]{8,})"), _assignment),
]


def redact(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text
