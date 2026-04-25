# Price per 1M tokens in USD (Last Updated: 2026-04-25)
# Includes 2026 flagship models detected in session traces.

PRICING = {
    # --- Claude 4 Series (Anthropic) ---
    "claude-4.7-opus":   {"in": 5.00, "out": 25.00, "cached_read": 0.50},
    "claude-4.5-opus":   {"in": 5.00, "out": 25.00, "cached_read": 0.50},
    "claude-4.6-sonnet": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-4.5-haiku":  {"in": 1.00, "out": 5.00,  "cached_read": 0.10},
    
    # Aliases/Versions for Claude 4
    "claude-opus-4-7":   {"in": 5.00, "out": 25.00, "cached_read": 0.50},
    "claude-opus-4-6":   {"in": 5.00, "out": 25.00, "cached_read": 0.50},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-haiku-4-5":  {"in": 1.00, "out": 5.00,  "cached_read": 0.10},
    "claude-haiku-4.5":  {"in": 1.00, "out": 5.00,  "cached_read": 0.10},  # dot variant emitted by some agents (Copilot)
    
    # Claude 3.5
    "claude-3-5-sonnet": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-3.5-sonnet": {"in": 3.00, "out": 15.00, "cached_read": 0.30},
    "claude-3.5-haiku":  {"in": 0.80, "out": 4.00,  "cached_read": 0.08},

    # --- GPT-5 Series (OpenAI) ---
    "gpt-5.5-pro":       {"in": 30.00, "out": 180.00, "cached_read": 3.00},
    "gpt-5.5-standard":  {"in": 5.00,  "out": 30.00,  "cached_read": 0.50},
    "gpt-5.4":           {"in": 2.50,  "out": 15.00,  "cached_read": 0.25},
    "gpt-5-mini":        {"in": 0.15,  "out": 0.60,   "cached_read": 0.015},
    "gpt-5":             {"in": 0.625, "out": 5.00,   "cached_read": 0.06},
    "gpt-4.1":           {"in": 2.50,  "out": 10.00,  "cached_read": 1.25},

    # --- Gemini 3 Series (Google) ---
    "gemini-3.1-pro":    {"in": 2.00, "out": 12.00, "cached_read": 0.20},
    "gemini-3.1-flash":  {"in": 0.25, "out": 1.50,  "cached_read": 0.025},
    "gemini-3-pro":      {"in": 2.00, "out": 12.00, "cached_read": 0.20},
    "gemini-3-flash":    {"in": 0.25, "out": 1.50,  "cached_read": 0.025},
    "auto-gemini-3":     {"in": 2.00, "out": 12.00, "cached_read": 0.20},  # auto-router targeting Gemini 3 (assume Pro tier)
    
    # Gemini 2.x
    "gemini-2.5-pro":    {"in": 1.25, "out": 5.00,  "cached_read": 0.125},
    "gemini-2.5-flash":  {"in": 0.15, "out": 0.60,  "cached_read": 0.015},
    "gemini-2.0-flash":  {"in": 0.075, "out": 0.30, "cached_read": 0.0075},
    "gemini":            {"in": 1.25, "out": 5.00,  "cached_read": 0.125}, # Default Gemini tier

    # --- Specialized & Local ---
    "devstral-2":        {"in": 0.40, "out": 0.90,  "cached_read": 0.04},
    "glm-5.1":           {"in": 1.15, "out": 3.75,  "cached_read": 0.115},
    "gemma4":            {"in": 0.00, "out": 0.00,  "cached_read": 0.00}, # Local
    "auto":              {"in": 3.00, "out": 15.00, "cached_read": 0.30}, # Typical 'auto' maps to Sonnet/GPT-4o
    
    # Default (Safe baseline for unknown models)
    "_default":          {"in": 2.00, "out": 10.00, "cached_read": 0.50}
}

PRICING_UPDATED = "2026-04-25"

def calculate_cost(model_name: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Returns estimated cost in USD based on 2026 model rates."""
    if not model_name:
        config = PRICING["_default"]
    else:
        model_name = str(model_name).lower()
        config = PRICING.get(model_name)
        if not config:
            # Try fuzzy prefix match (longer keys first)
            sorted_keys = sorted([k for k in PRICING.keys() if k != "_default"], key=len, reverse=True)
            for k in sorted_keys:
                if k in model_name: # More robust than startswith for names like "gemini (antigravity)"
                    config = PRICING[k]
                    break
        if not config:
            config = PRICING["_default"]
            
    in_cost = (input_tokens / 1_000_000) * config["in"]
    out_cost = (output_tokens / 1_000_000) * config["out"]
    
    # Use cached_read if available, otherwise 10% of input as default fallback for 2026 era
    cached_rate = config.get("cached_read", config["in"] * 0.1)
    cached_cost = (cached_tokens / 1_000_000) * cached_rate
    
    return in_cost + out_cost + cached_cost
