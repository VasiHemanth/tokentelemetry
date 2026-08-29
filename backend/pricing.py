# Price per 1M tokens in USD (Last Updated: 2026-05-17)
#
# Two-tier lookup:
#   1. PRICING_BY_PROVIDER  — (provider, model_id_lower) → rates. Authoritative
#      when we know which provider served the call (Hermes records this in
#      sessions.billing_provider).
#   2. PRICING (flat)       — model_id_lower → rates. Used when provider is
#      unknown OR provider-keyed lookup misses. Direct-provider prices are
#      treated as canonical.
#
# Same model on different providers can cost very different things. Example:
#   deepseek-v4-pro on DeepSeek direct: $0.66 in / $1.98 out (off-peak)
#   deepseek-v4-pro on Together:        $2.10 in / $4.40 out
#   deepseek-v4-pro on Fireworks:       $1.74 in / $3.48 out
# Don't flatten — keep provider-keyed entries where they conflict.
#
# Sources cited in PRICING_SOURCES.md alongside this file.

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Date the CURATED inline tables below were last hand-checked against provider
# price lists. This is deliberately NOT overwritten by the bundled overlay:
# the two move independently, and reporting the overlay's date for the inline
# table hid a three-month-stale DeepSeek rate behind a fresh-looking timestamp.
PRICING_UPDATED = "2026-08-29"
# Date of the bundled models.dev snapshot. Set by _load_bundled_pricing().
PRICING_OVERLAY_UPDATED = None

# Build-time pricing dataset (models.dev), refreshed maintainer/CI-side and
# committed alongside this module — see pricing_sync.py. We read ONLY this
# bundled file from the package directory; pricing.py performs ZERO network I/O
# at import or runtime. The inline PRICING / PRICING_BY_PROVIDER dicts below
# stay as the curated, authoritative fallback (and the fallback if the bundled
# file is absent or malformed). The overlay fills in the long tail of models the
# inline tables don't cover, without clobbering the hand-tuned entries.
_PRICING_DATA_PATH = Path(__file__).parent / "pricing_data.json"
# Separator used by pricing_sync.py to flatten (provider, model) tuples into the
# JSON string keys of the "by_provider" map.
_PROVIDER_SEP = "\x00"

# Direct first-party pricing — used as the flat-fallback when provider unknown.
PRICING = {
    # --- Anthropic (Claude) ---
    "claude-opus-4-7":   {"in": 5.00,  "out": 25.00, "cached_read": 0.50},
    "claude-opus-4-6":   {"in": 5.00,  "out": 25.00, "cached_read": 0.50},
    "claude-opus-4-5":   {"in": 5.00,  "out": 25.00, "cached_read": 0.50},
    "claude-opus-4-1":   {"in": 15.00, "out": 75.00, "cached_read": 1.50},
    "claude-opus-4":     {"in": 15.00, "out": 75.00, "cached_read": 1.50},
    "claude-sonnet-4-6": {"in": 3.00,  "out": 15.00, "cached_read": 0.30},
    "claude-sonnet-4-5": {"in": 3.00,  "out": 15.00, "cached_read": 0.30},
    "claude-sonnet-4":   {"in": 3.00,  "out": 15.00, "cached_read": 0.30},
    "claude-haiku-4-5":  {"in": 1.00,  "out": 5.00,  "cached_read": 0.10},
    "claude-haiku-4.5":  {"in": 1.00,  "out": 5.00,  "cached_read": 0.10},  # dot variant emitted by Copilot

    # Older Claude (still served)
    "claude-3-5-sonnet": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-3.5-sonnet": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-3.5-haiku":  {"in": 0.80, "out": 4.00,  "cached_read": 0.08},

    # --- OpenAI (GPT-5 series) ---
    # --- GPT-5.6 (Sol / Terra / Luna) ---
    # Current rates. Both cuts are date-banded in PRICING_HISTORY below, so a
    # session from before a cut is still priced at what it actually cost.
    # Sol's $4/$20 is promotional and guaranteed only through 2026-11-21; if it
    # reverts, that becomes a third band rather than an edit to these numbers.
    "gpt-5.6-sol":       {"in": 4.00,  "out": 20.00, "cached_read": 0.40},
    "gpt-5.6-terra":     {"in": 2.00,  "out": 12.00, "cached_read": 0.20},
    "gpt-5.6-luna":      {"in": 0.20,  "out": 1.20,  "cached_read": 0.02},
    "gpt-5.6":           {"in": 4.00,  "out": 20.00, "cached_read": 0.40},

    "gpt-5.5":           {"in": 5.00,  "out": 30.00, "cached_read": 0.50},
    "gpt-5-5":           {"in": 5.00,  "out": 30.00, "cached_read": 0.50},
    "gpt-5.5-pro":       {"in": 30.00, "out": 180.00, "cached_read": 3.00},
    "gpt-5.5-standard":  {"in": 5.00,  "out": 30.00,  "cached_read": 0.50},
    "gpt-5.4":           {"in": 2.50,  "out": 15.00, "cached_read": 0.25},
    "gpt-5-4":           {"in": 2.50,  "out": 15.00, "cached_read": 0.25},
    "gpt-5.4-mini":      {"in": 0.75,  "out": 4.50,  "cached_read": 0.075},
    "gpt-5-4-mini":      {"in": 0.75,  "out": 4.50,  "cached_read": 0.075},
    "gpt-5-mini":        {"in": 0.15,  "out": 0.60,  "cached_read": 0.015},
    "gpt-5":             {"in": 1.25,  "out": 10.00, "cached_read": 0.125},
    "gpt-4.1":           {"in": 2.50,  "out": 10.00, "cached_read": 1.25},

    # --- Google (Gemini) ---
    "gemini-3.1-pro":               {"in": 2.00,  "out": 12.00, "cached_read": 0.20},
    "gemini-3.1-flash":             {"in": 0.25,  "out": 1.50,  "cached_read": 0.025},
    "gemini-3.1-flash-lite":        {"in": 0.25,  "out": 1.50,  "cached_read": 0.025},
    "gemini-3.1-flash-live-preview": {"in": 0.75, "out": 4.50,  "cached_read": None},
    "gemini-3-pro":                 {"in": 2.00,  "out": 12.00, "cached_read": 0.20},
    "gemini-3-flash":               {"in": 0.25,  "out": 1.50,  "cached_read": 0.025},
    "gemini-3-flash-preview":       {"in": 0.25,  "out": 1.50,  "cached_read": 0.025},  # canonical flash pricing pending Google confirmation
    "auto-gemini-3":                {"in": 2.00,  "out": 12.00, "cached_read": 0.20},
    "gemini-2.5-pro":               {"in": 1.25,  "out": 10.00, "cached_read": 0.125},
    "gemini-2.5-flash":             {"in": 0.30,  "out": 2.50,  "cached_read": 0.03},
    "gemini-2.5-flash-lite":        {"in": 0.075, "out": 0.30,  "cached_read": 0.01},
    "gemini-2.5-flash-native-audio-preview-12-2025": {"in": 0.50, "out": 2.00, "cached_read": None},
    "gemini-2.5-computer-use-preview-10-2025":       {"in": 1.25, "out": 10.00, "cached_read": None},
    "gemini-2.0-flash":             {"in": 0.075, "out": 0.30,  "cached_read": 0.0075},
    "gemini":                       {"in": 1.25,  "out": 5.00,  "cached_read": 0.125},

    # --- DeepSeek (direct) ---
    # OFF-PEAK rates, per DeepSeek's 2026-08-16 repricing.
    # https://api-docs.deepseek.com/quick_start/pricing
    #
    # DeepSeek bills two rates by clock time: peak (01:00-04:00 and 06:00-10:00
    # UTC, Mon-Fri) costs exactly 2x off-peak. calculate_cost carries ONE rate
    # per model and takes no timestamp, and a session routinely spans both
    # windows anyway, so a single rate is the only thing this schema can express.
    # We bill off-peak because that is the list price the docs lead with; a
    # session that ran entirely in peak hours is therefore understated 2x.
    # Don't "fix" this by halving/doubling — plumb a timestamp or leave it.
    #
    # vision-exp is listed explicitly rather than left to the fuzzy prefix
    # matcher. It happens to share flash's rates today, but _fuzzy_key_matches
    # would silently price ANY deepseek-v4-flash-* variant at flash's rate,
    # including a future one that costs something else.
    "deepseek-v4-flash":            {"in": 0.22,  "out": 0.66,  "cached_read": 0.007},
    "deepseek-v4-flash-vision-exp": {"in": 0.22,  "out": 0.66,  "cached_read": 0.007},
    "deepseek-chat":                {"in": 0.22,  "out": 0.66,  "cached_read": 0.007},
    "deepseek-reasoner":            {"in": 0.22,  "out": 0.66,  "cached_read": 0.007},
    "deepseek-v4-pro":              {"in": 0.66,  "out": 1.98,  "cached_read": 0.022},

    # --- xAI (Grok) ---
    # List prices are the <200k-prompt band. Requests whose prompt reaches
    # 200k tokens are billed at 2x all three rates for that request — see
    # calculate_xai_turn_cost. https://docs.x.ai/developers/models/grok-4.6
    "grok-4.6":                     {"in": 2.00,  "out": 6.00,  "cached_read": 0.50},
    "grok-4.6-latest":              {"in": 2.00,  "out": 6.00,  "cached_read": 0.50},
    "grok-4.5":                     {"in": 2.00,  "out": 6.00,  "cached_read": 0.30},
    "grok-4.3":                     {"in": 1.25,  "out": 2.50,  "cached_read": 0.20},
    "grok-4.3-latest":              {"in": 1.25,  "out": 2.50,  "cached_read": 0.20},
    # Grok Build — xAI's agentic coding CLI. Sessions record the model id as the
    # generic "grok-build"; the underlying model is grok-build-0.1 (256K context;
    # grok-code-fast-1 requests route here after 2026-05-15). API rates below.
    "grok-build":                   {"in": 0.20,  "out": 1.50,  "cached_read": None},
    "grok-build-0.1":               {"in": 0.20,  "out": 1.50,  "cached_read": None},
    "grok-code-fast-1":             {"in": 0.20,  "out": 1.50,  "cached_read": None},
    "grok-code-fast":               {"in": 0.20,  "out": 1.50,  "cached_read": None},

    # --- Moonshot (Kimi, direct) ---
    "kimi-k2.6":                    {"in": 0.95,  "out": 4.00,  "cached_read": 0.16},
    "kimi-k2.5":                    {"in": 0.60,  "out": 3.00,  "cached_read": 0.10},
    "kimi-k2-0905-preview":         {"in": 0.60,  "out": 2.50,  "cached_read": 0.15},
    "kimi-k2-0711-preview":         {"in": 0.60,  "out": 2.50,  "cached_read": 0.15},
    "kimi-k2-thinking":             {"in": 0.60,  "out": 2.50,  "cached_read": 0.15},
    "kimi-k2-turbo-preview":        {"in": 1.15,  "out": 8.00,  "cached_read": 0.15},
    "kimi-k2-thinking-turbo":       {"in": 1.15,  "out": 8.00,  "cached_read": 0.15},
    "moonshot-v1-8k":               {"in": 0.20,  "out": 2.00,  "cached_read": None},
    "moonshot-v1-32k":              {"in": 1.00,  "out": 3.00,  "cached_read": None},
    "moonshot-v1-128k":             {"in": 2.00,  "out": 5.00,  "cached_read": None},
    "moonshot-v1-8k-vision-preview":   {"in": 0.20, "out": 2.00, "cached_read": None},
    "moonshot-v1-32k-vision-preview":  {"in": 1.00, "out": 3.00, "cached_read": None},
    "moonshot-v1-128k-vision-preview": {"in": 2.00, "out": 5.00, "cached_read": None},

    # --- MiniMax (direct) ---
    "minimax-m2.7":                 {"in": 0.30,  "out": 1.20,  "cached_read": 0.06},
    "minimax-m2.7-highspeed":       {"in": 0.60,  "out": 2.40,  "cached_read": 0.06},
    "minimax-m2.5":                 {"in": 0.30,  "out": 1.20,  "cached_read": 0.03},

    # --- z.ai (GLM, direct) ---
    "glm-5.1":                      {"in": 0.80,  "out": 3.20,  "cached_read": None},
    "glm-4.6":                      {"in": 0.45,  "out": 1.80,  "cached_read": None},
    "glm-5":                        {"in": 1.00,  "out": 3.20,  "cached_read": None},

    # --- Alibaba (Qwen, DashScope direct) ---
    "qwen3-max":                    {"in": 1.20,  "out": 6.00,  "cached_read": None},
    "qwen3.6-max-preview":          {"in": 1.30,  "out": 7.80,  "cached_read": None},

    # --- Xiaomi (MiMo, direct) ---
    "mimo-v2-flash":                {"in": 0.10,  "out": 0.30,  "cached_read": 0.01},
    "mimo-v2-pro":                  {"in": 1.00,  "out": 3.00,  "cached_read": 0.20},
    "mimo-v2-omni":                 {"in": 0.40,  "out": 2.00,  "cached_read": 0.08},

    # --- Groq (served via Groq, plain model ids) ---
    "llama-3.3-70b-versatile":      {"in": 0.59,  "out": 0.79,  "cached_read": None},
    "llama-3.1-8b-instant":         {"in": 0.05,  "out": 0.08,  "cached_read": None},

    # --- Specialized & Local ---
    "devstral-2":                   {"in": 0.40,  "out": 0.90,  "cached_read": 0.04},
    "gemma4":                       {"in": 0.00,  "out": 0.00,  "cached_read": 0.00},
    "auto":                         {"in": 3.00,  "out": 15.00, "cached_read": 0.30},

    # Safe baseline
    "_default":                     {"in": 2.00,  "out": 10.00, "cached_read": 0.50},
}

# Provider-specific overrides. Hermes records billing_provider per session, so
# we use this when available to capture markup/discount on aggregator providers.
# Key: (provider_lower, model_id_lower)
PRICING_BY_PROVIDER = {
    # --- DeepSeek (direct) ---
    # These MUST exist even though they duplicate the flat table above.
    # models.dev ships ("deepseek", "deepseek-v4-pro") at $0.435/$0.87 — a rate
    # that predates the 2026-08-16 repricing and is ~2.3x under list. The
    # bundled overlay only skips a key when an inline entry already claims it
    # (see _load_bundled_pricing), so without these tuples the overlay wins for
    # any caller that passes provider="deepseek" and the same model prices 4x
    # apart depending on whether the scanner happened to supply a provider.
    ("deepseek", "deepseek-v4-flash"):               {"in": 0.22, "out": 0.66,  "cached_read": 0.007},
    ("deepseek", "deepseek-v4-flash-vision-exp"):    {"in": 0.22, "out": 0.66,  "cached_read": 0.007},
    ("deepseek", "deepseek-chat"):                   {"in": 0.22, "out": 0.66,  "cached_read": 0.007},
    ("deepseek", "deepseek-reasoner"):               {"in": 0.22, "out": 0.66,  "cached_read": 0.007},
    ("deepseek", "deepseek-v4-pro"):                 {"in": 0.66, "out": 1.98,  "cached_read": 0.022},

    # --- OpenAI (direct) ---
    # The overlay disagrees with itself on this family: its flat gpt-5.6-luna is
    # the pre-cut $1.00/$6.00 while its openai-keyed one is the current
    # $0.20/$1.20. Pin the direct rates so the lookup is not decided by which
    # table happened to be consulted.
    ("openai", "gpt-5.6-sol"):                       {"in": 4.00, "out": 20.00, "cached_read": 0.40},
    ("openai", "gpt-5.6-terra"):                     {"in": 2.00, "out": 12.00, "cached_read": 0.20},
    ("openai", "gpt-5.6-luna"):                      {"in": 0.20, "out": 1.20,  "cached_read": 0.02},
    ("openai", "gpt-5.6"):                           {"in": 4.00, "out": 20.00, "cached_read": 0.40},

    # --- Together AI (aggregator markup) ---
    ("together", "glm-5.1"):                         {"in": 1.40, "out": 4.40,  "cached_read": None},
    ("together", "glm-5"):                           {"in": 1.00, "out": 3.20,  "cached_read": None},
    ("together", "minimax-m2.7"):                    {"in": 0.30, "out": 1.20,  "cached_read": 0.06},
    ("together", "minimax-m2.5"):                    {"in": 0.30, "out": 1.20,  "cached_read": 0.06},
    ("together", "kimi-k2.6"):                       {"in": 1.20, "out": 4.50,  "cached_read": 0.20},
    ("together", "kimi-k2.5"):                       {"in": 0.50, "out": 2.80,  "cached_read": None},
    ("together", "deepseek-v4-pro"):                 {"in": 2.10, "out": 4.40,  "cached_read": 0.20},
    ("together", "qwen3.6-plus"):                    {"in": 0.50, "out": 3.00,  "cached_read": None},
    ("together", "qwen3.5-397b-a17b"):               {"in": 0.60, "out": 3.60,  "cached_read": None},
    ("together", "qwen3.5-9b"):                      {"in": 0.10, "out": 0.15,  "cached_read": None},
    ("together", "qwen3-235b-a22b-fp8-tput"):        {"in": 0.20, "out": 0.60,  "cached_read": None},
    ("together", "qwen3-coder-480b-a35b-instruct"):  {"in": 2.00, "out": 2.00,  "cached_read": None},
    ("together", "gpt-oss-120b"):                    {"in": 0.15, "out": 0.60,  "cached_read": None},
    ("together", "gpt-oss-20b"):                     {"in": 0.05, "out": 0.20,  "cached_read": None},
    ("together", "llama-3.3-70b"):                   {"in": 0.88, "out": 0.88,  "cached_read": None},
    ("together", "llama-3-8b-instruct-lite"):        {"in": 0.10, "out": 0.10,  "cached_read": None},

    # --- Fireworks AI (aggregator) ---
    ("fireworks", "kimi-k2p6"):                      {"in": 0.95, "out": 4.00,  "cached_read": 0.16},
    ("fireworks", "kimi-k2.6"):                      {"in": 0.95, "out": 4.00,  "cached_read": 0.16},
    ("fireworks", "kimi-k2p5"):                      {"in": 0.60, "out": 3.00,  "cached_read": 0.10},
    ("fireworks", "kimi-k2.5"):                      {"in": 0.60, "out": 3.00,  "cached_read": 0.10},
    ("fireworks", "deepseek-v4-pro"):                {"in": 1.74, "out": 3.48,  "cached_read": 0.145},
    ("fireworks", "glm-5p1"):                        {"in": 1.40, "out": 4.40,  "cached_read": 0.26},
    ("fireworks", "glm-5.1"):                        {"in": 1.40, "out": 4.40,  "cached_read": 0.26},
    ("fireworks", "minimax-m2p7"):                   {"in": 0.30, "out": 1.20,  "cached_read": 0.06},
    ("fireworks", "minimax-m2.7"):                   {"in": 0.30, "out": 1.20,  "cached_read": 0.06},
    ("fireworks", "minimax-m2p5"):                   {"in": 0.30, "out": 1.20,  "cached_read": 0.03},
    ("fireworks", "minimax-m2.5"):                   {"in": 0.30, "out": 1.20,  "cached_read": 0.03},
    ("fireworks", "gpt-oss-120b"):                   {"in": 0.15, "out": 0.60,  "cached_read": 0.015},
    ("fireworks", "gpt-oss-20b"):                    {"in": 0.07, "out": 0.30,  "cached_read": 0.035},

    # --- Groq (provider-specific model paths) ---
    ("groq", "openai/gpt-oss-20b"):                  {"in": 0.075, "out": 0.30, "cached_read": 0.0375},
    ("groq", "openai/gpt-oss-safeguard-20b"):        {"in": 0.075, "out": 0.30, "cached_read": None},
    ("groq", "openai/gpt-oss-120b"):                 {"in": 0.15,  "out": 0.60, "cached_read": 0.075},
    ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"): {"in": 0.11, "out": 0.34, "cached_read": None},
    ("groq", "qwen/qwen3-32b"):                      {"in": 0.29, "out": 0.59, "cached_read": None},
    ("groq", "moonshotai/kimi-k2-instruct-0905"):    {"in": 1.00, "out": 3.00, "cached_read": 0.50},
    ("groq", "llama-3.3-70b-versatile"):             {"in": 0.59, "out": 0.79, "cached_read": None},
    ("groq", "llama-3.1-8b-instant"):                {"in": 0.05, "out": 0.08, "cached_read": None},
}


def _coerce_rates(value) -> Optional[dict]:
    """Validate one overlay entry → {in, out, cached_read} with float|None values.

    Returns None for anything that isn't a usable rate dict, so malformed entries
    are skipped rather than poisoning the table.
    """
    if not isinstance(value, dict):
        return None
    out = {}
    for key in ("in", "out", "cached_read"):
        raw = value.get(key)
        if raw is None:
            out[key] = None
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        out[key] = float(raw)
    # Need at least one priced direction to be meaningful.
    if out["in"] is None and out["out"] is None:
        return None
    return out


def _load_bundled_pricing() -> None:
    """Overlay the committed pricing_data.json onto the inline tables, in place.

    Pure local file read — NO network I/O. Inline dict entries always win
    (curated/authoritative); the overlay only adds models not already present,
    giving us broad models.dev coverage without clobbering hand-tuned prices.
    Any failure (missing file, bad JSON, wrong shape) is swallowed so the module
    falls back cleanly to the static tables.
    """
    try:
        raw = _PRICING_DATA_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return

    flat = data.get("pricing")
    if isinstance(flat, dict):
        for model_id, rates in flat.items():
            if not isinstance(model_id, str):
                continue
            key = model_id.lower().strip()
            if not key or key in PRICING:
                continue  # inline entry is authoritative
            coerced = _coerce_rates(rates)
            if coerced is not None:
                PRICING[key] = coerced

    by_provider = data.get("by_provider")
    if isinstance(by_provider, dict):
        for combined, rates in by_provider.items():
            if not isinstance(combined, str) or _PROVIDER_SEP not in combined:
                continue
            provider, model_id = combined.split(_PROVIDER_SEP, 1)
            tup = (provider.lower().strip(), model_id.lower().strip())
            if not tup[0] or not tup[1] or tup in PRICING_BY_PROVIDER:
                continue  # inline entry is authoritative
            coerced = _coerce_rates(rates)
            if coerced is not None:
                PRICING_BY_PROVIDER[tup] = coerced

    updated = data.get("updated")
    if isinstance(updated, str) and updated.strip():
        global PRICING_OVERLAY_UPDATED
        PRICING_OVERLAY_UPDATED = updated.strip()


_load_bundled_pricing()


# ---------------------------------------------------------------------------
# Historical rates
# ---------------------------------------------------------------------------
# A provider that reprices does not reprice the past. Tokens generated in July
# were billed at July's rate, and re-costing an old session at today's rate
# makes a user's spend history silently wrong — which is exactly what correcting
# the DeepSeek tables did before these bands existed (#303).
#
# Each entry is a list of (effective_from, rates) ascending. A band applies from
# its instant until the next band starts; a timestamp older than the first band
# uses the first band. The LAST band must equal the model's entry in the tables
# above — test_pricing_history.py asserts this, so the two can't drift.
#
# Only models whose price actually MOVED belong here. Everything else resolves
# through the normal tables and is unaffected, so this stays small.
#
# Timestamps are UTC. DeepSeek's cutover has a published time (16:00 UTC); the
# OpenAI cuts were announced by date only, so those bands start at 00:00 UTC and
# a session on the cut date itself may be off by up to a day. Recorded here
# rather than hidden, because it is the one imprecise thing in this table.
_DEEPSEEK_BANDS = {
    # https://api-docs.deepseek.com/quick_start/pricing — V4 repricing, and the
    # point peak/off-peak was introduced. Post-cut rates are OFF-PEAK; see the
    # note on the DeepSeek block above.
    #
    # V4-Pro's pre-cut band is $0.435/$0.87, NOT the $1.74/$3.48 list price. Pro
    # launched at list in April 2026 under a 75% promotion that was extended past
    # its stated 31 May deadline and remained the effective price until the
    # repricing. Billing the list price would overstate every pre-August Pro
    # session by 4x.
    "deepseek-v4-flash": [
        ("2000-01-01T00:00:00Z", {"in": 0.14, "out": 0.28, "cached_read": 0.0028}),
        ("2026-08-16T16:00:00Z", {"in": 0.22, "out": 0.66, "cached_read": 0.007}),
    ],
    "deepseek-v4-flash-vision-exp": [
        ("2000-01-01T00:00:00Z", {"in": 0.14, "out": 0.28, "cached_read": 0.0028}),
        ("2026-08-16T16:00:00Z", {"in": 0.22, "out": 0.66, "cached_read": 0.007}),
    ],
    # deepseek-chat / deepseek-reasoner are DeepSeek's own API aliases and moved
    # with the same repricing. Their PRE-cut band is the $0.14/$0.28 this repo's
    # curated table recorded at its 2026-05-17 hand-check, not models.dev's
    # $0.29/$0.43 — that figure is an aggregator's rate for the same name, and
    # these bands describe DeepSeek direct. Flagged because it is the one band
    # here taken from a prior hand-check rather than the provider's price list.
    "deepseek-chat": [
        ("2000-01-01T00:00:00Z", {"in": 0.14, "out": 0.28, "cached_read": 0.0028}),
        ("2026-08-16T16:00:00Z", {"in": 0.22, "out": 0.66, "cached_read": 0.007}),
    ],
    "deepseek-reasoner": [
        ("2000-01-01T00:00:00Z", {"in": 0.14, "out": 0.28, "cached_read": 0.0028}),
        ("2026-08-16T16:00:00Z", {"in": 0.22, "out": 0.66, "cached_read": 0.007}),
    ],
    "deepseek-v4-pro": [
        ("2000-01-01T00:00:00Z", {"in": 0.435, "out": 0.87, "cached_read": 0.003625}),
        ("2026-08-16T16:00:00Z", {"in": 0.66,  "out": 1.98, "cached_read": 0.022}),
    ],
}

_GPT56_BANDS = {
    # 2026-07-30: Terra cut 20%, Luna cut 80%, Sol unchanged.
    # 2026-08-22: Sol cut to $4/$20 from $5/$30 (promotional, held to 2026-11-21).
    # Pre-cut cached-read rates are 10% of input, the ratio every published
    # GPT-5.6 rate uses and the value the models.dev snapshot carries for the
    # pre-cut prices.
    "gpt-5.6-sol": [
        ("2000-01-01T00:00:00Z", {"in": 5.00, "out": 30.00, "cached_read": 0.50}),
        ("2026-08-22T00:00:00Z", {"in": 4.00, "out": 20.00, "cached_read": 0.40}),
    ],
    "gpt-5.6": [
        ("2000-01-01T00:00:00Z", {"in": 5.00, "out": 30.00, "cached_read": 0.50}),
        ("2026-08-22T00:00:00Z", {"in": 4.00, "out": 20.00, "cached_read": 0.40}),
    ],
    "gpt-5.6-terra": [
        ("2000-01-01T00:00:00Z", {"in": 2.50, "out": 15.00, "cached_read": 0.25}),
        ("2026-07-30T00:00:00Z", {"in": 2.00, "out": 12.00, "cached_read": 0.20}),
    ],
    "gpt-5.6-luna": [
        ("2000-01-01T00:00:00Z", {"in": 1.00, "out": 6.00,  "cached_read": 0.10}),
        ("2026-07-30T00:00:00Z", {"in": 0.20, "out": 1.20,  "cached_read": 0.02}),
    ],
}

PRICING_HISTORY: dict = {**_DEEPSEEK_BANDS, **_GPT56_BANDS}

# Same bands, keyed by (provider, model) so a provider-qualified lookup gets the
# historical rate too. Built from the same source so the two can never disagree.
PRICING_BY_PROVIDER_HISTORY: dict = {}
for _m, _b in _DEEPSEEK_BANDS.items():
    PRICING_BY_PROVIDER_HISTORY[("deepseek", _m)] = _b
for _m, _b in _GPT56_BANDS.items():
    PRICING_BY_PROVIDER_HISTORY[("openai", _m)] = _b


def _as_utc(at) -> Optional[datetime]:
    """Coerce a datetime or ISO-8601 string to an aware UTC datetime.

    A naive datetime is assumed UTC rather than local: session timestamps reach
    us from a dozen harnesses and guessing a local zone would shift a session
    across a repricing boundary by hours. Unparseable input returns None, which
    makes the caller fall back to current rates.
    """
    if at is None:
        return None
    if isinstance(at, str):
        txt = at.strip()
        if not txt:
            return None
        try:
            at = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(at, datetime):
        return None
    if at.tzinfo is None:
        return at.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc)


def _rates_at(bands, at: datetime) -> Dict[str, Any]:
    """The band in force at ``at``. Older than every band → the earliest one."""
    chosen = bands[0][1]
    for start, rates in bands:
        if at >= _as_utc(start):
            chosen = rates
        else:
            break
    return chosen


def rates_for(model: str, provider: Optional[str] = None, at=None) -> Optional[Dict[str, Any]]:
    """Historical rates for a model at a point in time, or None if not banded."""
    when = _as_utc(at)
    if when is None or not model:
        return None
    m = _normalize_model_id(str(model))
    if provider:
        bands = PRICING_BY_PROVIDER_HISTORY.get((str(provider).lower().strip(), m))
        if bands:
            return _rates_at(bands, when)
    bands = PRICING_HISTORY.get(m)
    return _rates_at(bands, when) if bands else None


# xAI long-context cliff: a request whose prompt reaches this many tokens is
# billed at 2x the <200k list rates for every token in that request (input,
# cached input, and output). Applies per request, not per session.
XAI_LONG_PROMPT_THRESHOLD = 200_000


def _fuzzy_key_matches(key: str, model: str) -> bool:
    """Substring match that refuses a shorter dotted version prefix.

    ``grok-4`` must not win for ``grok-4.6`` (that used to silently bill at
    grok-4's $3/$15). ``grok-4`` may still match ``grok-4-fast-reasoning``.
    """
    idx = model.find(key)
    if idx < 0:
        return False
    after = model[idx + len(key):]
    if after[:1] == "." and after[1:2].isdigit():
        return False
    return True


def _normalize_model_id(model: str) -> str:
    """Lowercase and strip common aggregator namespace prefixes."""
    m = model.lower().strip()
    # Aggregators sometimes emit "fireworks/foo" or "together/bar"; strip the
    # prefix because billing_provider already tells us the routing.
    for prefix in ("fireworks/", "together/", "openrouter/"):
        if m.startswith(prefix):
            m = m[len(prefix):]
            break
    return m


def calculate_cost(
    model_name: Optional[str],
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    provider: Optional[str] = None,
    cache_creation_tokens: int = 0,
    cache_creation_1h_tokens: int = 0,
    endpoint: Optional[str] = None,
    tok_per_sec: Optional[float] = None,
    billing_mode: Optional[str] = None,
    at=None,
) -> float:
    """Estimate cost in USD. Prefer (provider, model) when provider is known.

    ``cache_creation_tokens`` are prompt-cache WRITE tokens (Anthropic's
    ``cache_creation_input_tokens``). Anthropic bills these at 1.25x the input
    rate — distinct from ``cached_tokens`` (cache READ), billed at the much
    cheaper ``cached_read`` rate. Defaults to 0 so existing positional callers
    are unaffected.

    ``at`` is when the tokens were generated (datetime or ISO string). Models
    whose price changed on a known date are listed in PRICING_HISTORY; passing
    ``at`` prices those at the rate in force THEN rather than now, so correcting
    a table doesn't silently rewrite a user's spend history. Omitting it keeps
    the previous behaviour exactly: current rates for everything.

    ``endpoint`` and ``tok_per_sec`` are optional and only affect the
    local/subscription branches: if the session was served by a flat-subscription
    endpoint the per-call cost is 0 (billed monthly), and a local model with no
    API rate is priced by its electricity draw. All callers that omit these get
    the unchanged per-token behaviour.
    """
    # --- LOOKUP region -----------------------------------------------------
    # Subscription / local-model branches go FIRST so they short-circuit before
    # the per-token rate-math at the bottom. Both are opt-in via
    # ~/.tokentelemetry/power.json; with no config the substring match never
    # fires and unpriced models fall through to _default as before.
    if endpoint:
        try:
            from power_config import is_subscription_endpoint
            if is_subscription_endpoint(endpoint):
                # Flat monthly subscription — per-call cost is tracked separately.
                return 0.0
        except Exception:
            pass

    # Model-level flat subscription: a specific model billed monthly regardless of
    # which endpoint served it (one proxy can front both subscription and
    # pay-per-token models). Opt-in via power.json subscriptionModels; empty by default.
    try:
        from power_config import is_subscription_model
        if is_subscription_model(model_name):
            return 0.0
    except Exception:
        pass

    # Provider-level flat subscription. Same idea as the endpoint branch above,
    # keyed on the provider id instead — some harnesses record a provider and no
    # endpoint at all (Cline's sessions.db has a `provider` column and no base
    # URL), so routing like `cline-pass` is unreachable by endpoint matching.
    # Opt-in via power.json subscriptionProviders; empty by default.
    try:
        from power_config import is_subscription_provider
        if is_subscription_provider(provider):
            return 0.0
    except Exception:
        pass

    # Confirmed-local sessions (loopback/local endpoint, a local provider id, or
    # the agent set to `local` billing mode) are priced by electricity and WIN
    # over the pricing table — so a local llama-3.3-70b isn't billed at cloud
    # rates, and gemma4 isn't reported as free. Throughput is the measured rate
    # when the caller has one, else a model-size-based default.
    try:
        from power_config import (
            is_local_session, load_power_config, electricity_cost,
            default_tok_per_sec_for_model,
        )
        if is_local_session(model_name, endpoint, provider, billing_mode):
            return electricity_cost(
                output_tokens,
                config=load_power_config(),
                tok_per_sec=tok_per_sec or default_tok_per_sec_for_model(model_name),
            )
    except Exception:
        pass

    if not model_name:
        config = PRICING["_default"]
    else:
        m_norm = _normalize_model_id(str(model_name))
        # A dated rate beats both tables: the tables hold today's price, and for
        # a session that predates a repricing today's price is the wrong answer.
        config = rates_for(m_norm, provider, at)
        if provider and not config:
            config = PRICING_BY_PROVIDER.get((provider.lower(), m_norm))
        if not config:
            config = PRICING.get(m_norm)
        if not config:
            # Fuzzy prefix match against the flat table (longer keys first)
            sorted_keys = sorted([k for k in PRICING.keys() if k != "_default"], key=len, reverse=True)
            for k in sorted_keys:
                if _fuzzy_key_matches(k, m_norm):
                    config = PRICING[k]
                    break
        if not config:
            # No known API rate for this model. If the user has opted in via
            # ~/.tokentelemetry/power.json, treat it as a local model and price
            # it by electricity instead of the (wrong) _default per-token rate.
            try:
                from power_config import (
                    local_power_enabled, load_power_config, electricity_cost,
                    default_tok_per_sec_for_model,
                )
                if local_power_enabled():
                    pc = load_power_config()
                    return electricity_cost(
                        output_tokens,
                        config=pc,
                        tok_per_sec=tok_per_sec or default_tok_per_sec_for_model(model_name),
                    )
            except Exception:
                pass
            config = PRICING["_default"]

    in_rate = config["in"] or 0
    out_rate = config["out"] or 0
    cached_rate = config.get("cached_read")
    if cached_rate is None:
        cached_rate = in_rate * 0.1  # 2026-era default: cached read ≈ 10% of input

    # Prompt-cache WRITE tokens cost 1.25x the input rate for 5m TTL, 2x for 1h TTL (Anthropic billing).
    cache_write_rate = in_rate * 1.25
    cache_write_1h_rate = in_rate * 2.0

    in_cost = (input_tokens / 1_000_000) * in_rate
    out_cost = (output_tokens / 1_000_000) * out_rate
    cached_cost = (cached_tokens / 1_000_000) * cached_rate

    cc_1h = min(cache_creation_1h_tokens or 0, cache_creation_tokens or 0)
    cc_5m = (cache_creation_tokens or 0) - cc_1h

    cache_write_cost = (cc_5m / 1_000_000) * cache_write_rate + (cc_1h / 1_000_000) * cache_write_1h_rate
    return in_cost + out_cost + cached_cost + cache_write_cost


def calculate_xai_turn_cost(
    model_name: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Price one xAI request, applying the 200k-prompt 2x cliff.

    ``prompt_tokens`` is the full prompt (cached + uncached). Uncached input is
    ``prompt − cached``. The 2x multiplier applies to the whole request when
    the prompt reaches ``XAI_LONG_PROMPT_THRESHOLD``.
    """
    prompt = max(int(prompt_tokens or 0), 0)
    cached = min(max(int(cached_tokens or 0), 0), prompt)
    uncached = prompt - cached
    completion = max(int(completion_tokens or 0), 0)
    cost = calculate_cost(model_name, uncached, completion, cached)
    if prompt >= XAI_LONG_PROMPT_THRESHOLD:
        return cost * 2.0
    return cost
