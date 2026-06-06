"""Summarizer backend registry.

Adapters register here. Only adapters whose CLI is installed are offered to the
frontend, so the onboarding picker shows exactly what the user can actually run.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseSummarizer, SummarizerError
from .claude import ClaudeSummarizer
from .codex import CodexSummarizer
from .gemini import GeminiSummarizer
from .antigravity import AntigravitySummarizer
from .ollama import OllamaSummarizer
from .openai_compat import OpenAICompatSummarizer
from .qwen import QwenSummarizer

# Only adapters whose CLI is installed are offered to the frontend.
# openai_compat is the exception — it has no CLI to install, so it always shows
# as the universal "point it at any OpenAI-compatible server" option.
_ALL: List[BaseSummarizer] = [
    ClaudeSummarizer(),
    CodexSummarizer(),
    GeminiSummarizer(),
    AntigravitySummarizer(),
    QwenSummarizer(),
    OllamaSummarizer(),
    OpenAICompatSummarizer(),
]

_BY_NAME: Dict[str, BaseSummarizer] = {s.name: s for s in _ALL}

# Every backend name the registry knows about, installed or not. Used to
# validate persisted config so an unknown ``backend`` value can't be saved and
# then silently disable summaries (#57).
KNOWN_BACKENDS: frozenset[str] = frozenset(_BY_NAME)


def get_summarizer(
    name: str,
    model: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Optional[BaseSummarizer]:
    """Look up a backend by name. If a ``model`` is supplied, return a fresh
    instance bound to that model (Ollama / Codex support this) rather than
    the registry singleton. ``options`` carries backend-specific config — for
    openai_compat that's the endpoint + sampling params."""
    if name == "ollama" and model:
        return OllamaSummarizer(model=model)
    if name == "codex" and model:
        return CodexSummarizer(model=model)
    if name == "openai_compat":
        return OpenAICompatSummarizer(model=model, config=options or {})
    return _BY_NAME.get(name)


def available_summarizers() -> List[BaseSummarizer]:
    """Installed, runnable backends — what onboarding should offer."""
    return [s for s in _ALL if s.is_available()]


__all__ = [
    "BaseSummarizer",
    "SummarizerError",
    "get_summarizer",
    "available_summarizers",
    "KNOWN_BACKENDS",
]
