"""
config.py - Central Configuration
Project: Docstract - Intelligent Document Processor
Author: Ankur Sharma

WHY THIS FILE EXISTS:
    Previously, changing the model required updating TWO files:
    extractor.py AND batch_processor.py. That's a maintenance
    problem — easy to update one and forget the other, causing
    mismatched model/pricing calculations.

    Now: change ONE value here, everything updates automatically.

HOW TO SWITCH PROVIDERS:
    1. Change ACTIVE_PROVIDER to your chosen provider key
    2. Set the correct MODEL name for that provider
    3. Make sure your API key is in .env
    That's it. Nothing else needs to change.

SUPPORTED PROVIDERS:
    "groq"               → Llama 3.3 70B (free)
    "openai_gpt4o_mini"  → GPT-4o Mini
    "openai_gpt4o"       → GPT-4o
    "anthropic_haiku"    → Claude 3.5 Haiku
    "anthropic_sonnet"   → Claude 3.5 Sonnet
    "google_flash"       → Gemini 1.5 Flash
    "google_pro"         → Gemini 1.5 Pro
    "mistral_small"      → Mistral Small
    "mistral_large"      → Mistral Large
    "custom"             → Set your own model + pricing
"""


# ═══════════════════════════════════════════════════════════
# ✏️  CHANGE THESE TWO LINES TO SWITCH PROVIDERS
# ═══════════════════════════════════════════════════════════

ACTIVE_PROVIDER = "groq"
MODEL           = "llama-3.3-70b-versatile"

# ═══════════════════════════════════════════════════════════
# Everything below this line never needs to change
# unless a provider updates their pricing
# ═══════════════════════════════════════════════════════════


# ─────────────────────────────────────────────
# EXTRACTION SETTINGS
# ─────────────────────────────────────────────

TEMPERATURE = 0      # Always 0 for extraction (deterministic)
MAX_TOKENS  = 1000   # Max response length per extraction


# ─────────────────────────────────────────────
# PROVIDER PRICING REGISTRY
# ─────────────────────────────────────────────
# Prices in USD per 1 million tokens.
# Source: Official pricing pages as of 2025.
#
# To add a new provider:
#   1. Add an entry to PROVIDER_PRICING below
#   2. Set ACTIVE_PROVIDER and MODEL above
#   Done.

PROVIDER_PRICING = {
    "groq": {
        "name":   "Groq (Llama 3.3 70B)",
        "model":  "llama-3.3-70b-versatile",
        "input":  0.0,
        "output": 0.0,
        "free":   True
    },
    "openai_gpt4o_mini": {
        "name":   "OpenAI GPT-4o Mini",
        "model":  "gpt-4o-mini",
        "input":  0.150,
        "output": 0.600,
        "free":   False
    },
    "openai_gpt4o": {
        "name":   "OpenAI GPT-4o",
        "model":  "gpt-4o",
        "input":  2.50,
        "output": 10.00,
        "free":   False
    },
    "anthropic_haiku": {
        "name":   "Anthropic Claude 3.5 Haiku",
        "model":  "claude-3-5-haiku-20241022",
        "input":  0.80,
        "output": 4.00,
        "free":   False
    },
    "anthropic_sonnet": {
        "name":   "Anthropic Claude 3.5 Sonnet",
        "model":  "claude-3-5-sonnet-20241022",
        "input":  3.00,
        "output": 15.00,
        "free":   False
    },
    "google_flash": {
        "name":   "Google Gemini 1.5 Flash",
        "model":  "gemini-1.5-flash",
        "input":  0.075,
        "output": 0.30,
        "free":   False
    },
    "google_pro": {
        "name":   "Google Gemini 1.5 Pro",
        "model":  "gemini-1.5-pro",
        "input":  1.25,
        "output": 5.00,
        "free":   False
    },
    "mistral_small": {
        "name":   "Mistral Small",
        "model":  "mistral-small-latest",
        "input":  0.20,
        "output": 0.60,
        "free":   False
    },
    "mistral_large": {
        "name":   "Mistral Large",
        "model":  "mistral-large-latest",
        "input":  2.00,
        "output": 6.00,
        "free":   False
    },
    "custom": {
        "name":   "Custom Provider",
        "model":  "custom-model",
        "input":  0.0,    # ← set your price here
        "output": 0.0,    # ← set your price here
        "free":   False
    }
}


# ─────────────────────────────────────────────
# HELPER: Get active provider info
# ─────────────────────────────────────────────

def get_active_provider() -> dict:
    """
    Return the full config dict for the active provider.

    Returns:
        dict: Provider config including name, model, pricing
    """
    return PROVIDER_PRICING[ACTIVE_PROVIDER]


# ─────────────────────────────────────────────
# HELPER: Calculate cost
# ─────────────────────────────────────────────

def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate USD cost using the active provider's pricing.

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count

    Returns:
        float: Estimated cost in USD
    """
    provider    = get_active_provider()
    input_cost  = (prompt_tokens     / 1_000_000) * provider["input"]
    output_cost = (completion_tokens / 1_000_000) * provider["output"]
    return round(input_cost + output_cost, 6)


def calculate_cost_for_provider(
    prompt_tokens: int,
    completion_tokens: int,
    provider_key: str
) -> float:
    """
    Calculate cost for a SPECIFIC provider (used for comparisons).

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count
        provider_key (str): Key from PROVIDER_PRICING dict

    Returns:
        float: Estimated cost in USD
    """
    p           = PROVIDER_PRICING.get(provider_key, PROVIDER_PRICING["custom"])
    input_cost  = (prompt_tokens     / 1_000_000) * p["input"]
    output_cost = (completion_tokens / 1_000_000) * p["output"]
    return round(input_cost + output_cost, 6)


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def get_active_provider() -> dict:
    """
    Return the full config dict for the active provider.

    Returns:
        dict: Provider config including name, model, pricing
    """
    return PROVIDER_PRICING[ACTIVE_PROVIDER]


def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate USD cost using the active provider's pricing.

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count

    Returns:
        float: Estimated cost in USD
    """
    provider    = get_active_provider()
    input_cost  = (prompt_tokens     / 1_000_000) * provider["input"]
    output_cost = (completion_tokens / 1_000_000) * provider["output"]
    return round(input_cost + output_cost, 6)


def calculate_cost_for_provider(
    prompt_tokens: int,
    completion_tokens: int,
    provider_key: str
) -> float:
    """
    Calculate cost for a SPECIFIC provider (used for comparisons).

    Args:
        prompt_tokens (int): Input token count
        completion_tokens (int): Output token count
        provider_key (str): Key from PROVIDER_PRICING dict

    Returns:
        float: Estimated cost in USD
    """
    p           = PROVIDER_PRICING.get(provider_key, PROVIDER_PRICING["custom"])
    input_cost  = (prompt_tokens     / 1_000_000) * p["input"]
    output_cost = (completion_tokens / 1_000_000) * p["output"]
    return round(input_cost + output_cost, 6)
