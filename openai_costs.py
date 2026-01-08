from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TokenPricing:
    # USD per 1M tokens (so we avoid tiny decimals)
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


# IMPORTANT:
# - Pricing changes over time and can differ by account/region.
# - This is a *best-effort estimator* for your own tracking.
#
# Update these numbers to match your current pricing if you want accurate cost estimates.
DEFAULT_PRICING: dict[str, TokenPricing] = {
    # Prices per 1M tokens (Input / Cached input / Output)
    # From user's provided price list.
    "gpt-5.2": TokenPricing(input_per_million=1.75, cached_input_per_million=0.175, output_per_million=14.00),
    "gpt-5.1": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5-mini": TokenPricing(input_per_million=0.25, cached_input_per_million=0.025, output_per_million=2.00),
    "gpt-5-nano": TokenPricing(input_per_million=0.05, cached_input_per_million=0.005, output_per_million=0.40),
    "gpt-5.2-chat-latest": TokenPricing(input_per_million=1.75, cached_input_per_million=0.175, output_per_million=14.00),
    "gpt-5.1-chat-latest": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5-chat-latest": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5.1-codex-max": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5.1-codex": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5-codex": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-5.2-pro": TokenPricing(input_per_million=21.00, cached_input_per_million=0.0, output_per_million=168.00),
    "gpt-5-pro": TokenPricing(input_per_million=15.00, cached_input_per_million=0.0, output_per_million=120.00),
    "gpt-4.1": TokenPricing(input_per_million=2.00, cached_input_per_million=0.50, output_per_million=8.00),
    "gpt-4.1-mini": TokenPricing(input_per_million=0.40, cached_input_per_million=0.10, output_per_million=1.60),
    "gpt-4.1-nano": TokenPricing(input_per_million=0.10, cached_input_per_million=0.025, output_per_million=0.40),
    "gpt-4o": TokenPricing(input_per_million=2.50, cached_input_per_million=1.25, output_per_million=10.00),
    "gpt-4o-2024-05-13": TokenPricing(input_per_million=5.00, cached_input_per_million=0.0, output_per_million=15.00),
    "gpt-4o-mini": TokenPricing(input_per_million=0.15, cached_input_per_million=0.075, output_per_million=0.60),
    "gpt-realtime": TokenPricing(input_per_million=4.00, cached_input_per_million=0.40, output_per_million=16.00),
    "gpt-realtime-mini": TokenPricing(input_per_million=0.60, cached_input_per_million=0.06, output_per_million=2.40),
    "gpt-4o-realtime-preview": TokenPricing(input_per_million=5.00, cached_input_per_million=2.50, output_per_million=20.00),
    "gpt-4o-mini-realtime-preview": TokenPricing(input_per_million=0.60, cached_input_per_million=0.30, output_per_million=2.40),
    "gpt-audio": TokenPricing(input_per_million=2.50, cached_input_per_million=0.0, output_per_million=10.00),
    "gpt-audio-mini": TokenPricing(input_per_million=0.60, cached_input_per_million=0.0, output_per_million=2.40),
    "gpt-4o-audio-preview": TokenPricing(input_per_million=2.50, cached_input_per_million=0.0, output_per_million=10.00),
    "gpt-4o-mini-audio-preview": TokenPricing(input_per_million=0.15, cached_input_per_million=0.0, output_per_million=0.60),
    "o1": TokenPricing(input_per_million=15.00, cached_input_per_million=7.50, output_per_million=60.00),
    "o1-pro": TokenPricing(input_per_million=150.00, cached_input_per_million=0.0, output_per_million=600.00),
    "o3-pro": TokenPricing(input_per_million=20.00, cached_input_per_million=0.0, output_per_million=80.00),
    "o3": TokenPricing(input_per_million=2.00, cached_input_per_million=0.50, output_per_million=8.00),
    "o3-deep-research": TokenPricing(input_per_million=10.00, cached_input_per_million=2.50, output_per_million=40.00),
    "o4-mini": TokenPricing(input_per_million=1.10, cached_input_per_million=0.275, output_per_million=4.40),
    "o4-mini-deep-research": TokenPricing(input_per_million=2.00, cached_input_per_million=0.50, output_per_million=8.00),
    "o3-mini": TokenPricing(input_per_million=1.10, cached_input_per_million=0.55, output_per_million=4.40),
    "o1-mini": TokenPricing(input_per_million=1.10, cached_input_per_million=0.55, output_per_million=4.40),
    "gpt-5.1-codex-mini": TokenPricing(input_per_million=0.25, cached_input_per_million=0.025, output_per_million=2.00),
    "codex-mini-latest": TokenPricing(input_per_million=1.50, cached_input_per_million=0.375, output_per_million=6.00),
    "gpt-5-search-api": TokenPricing(input_per_million=1.25, cached_input_per_million=0.125, output_per_million=10.00),
    "gpt-4o-mini-search-preview": TokenPricing(input_per_million=0.15, cached_input_per_million=0.0, output_per_million=0.60),
    "gpt-4o-search-preview": TokenPricing(input_per_million=2.50, cached_input_per_million=0.0, output_per_million=10.00),
    "computer-use-preview": TokenPricing(input_per_million=3.00, cached_input_per_million=0.0, output_per_million=12.00),
    "gpt-image-1.5": TokenPricing(input_per_million=5.00, cached_input_per_million=1.25, output_per_million=10.00),
    "chatgpt-image-latest": TokenPricing(input_per_million=5.00, cached_input_per_million=1.25, output_per_million=10.00),
    "gpt-image-1": TokenPricing(input_per_million=5.00, cached_input_per_million=1.25, output_per_million=0.0),
    "gpt-image-1-mini": TokenPricing(input_per_million=2.00, cached_input_per_million=0.20, output_per_million=0.0),
}


def _resolve_pricing(model: str, pricing: dict[str, TokenPricing]) -> Optional[TokenPricing]:
    if model in pricing:
        return pricing[model]
    # Try to normalize common variant formats by progressively stripping suffix segments.
    # Example: "gpt-4o-2024-05-13" or vendor suffixes -> fall back to "gpt-4o" if present.
    parts = model.split("-")
    while len(parts) > 2:
        parts.pop()
        candidate = "-".join(parts)
        if candidate in pricing:
            return pricing[candidate]
    return None


def estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cached_input_tokens: Optional[int] = None,
    pricing: Optional[dict[str, TokenPricing]] = None,
) -> Optional[float]:
    if prompt_tokens is None and completion_tokens is None:
        return None

    pr = pricing or DEFAULT_PRICING
    p = _resolve_pricing(model, pr)
    if not p:
        return None

    in_tok = float(prompt_tokens or 0)
    cached_tok = float(cached_input_tokens or 0)
    out_tok = float(completion_tokens or 0)

    # cost = (tokens / 1_000_000) * price_per_million
    return (
        (in_tok / 1_000_000.0) * p.input_per_million
        + (cached_tok / 1_000_000.0) * p.cached_input_per_million
        + (out_tok / 1_000_000.0) * p.output_per_million
    )

