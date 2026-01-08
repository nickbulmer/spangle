from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TokenPricing:
    # USD per 1M tokens (so we avoid tiny decimals)
    input_per_million: float
    output_per_million: float


# IMPORTANT:
# - Pricing changes over time and can differ by account/region.
# - This is a *best-effort estimator* for your own tracking.
#
# Update these numbers to match your current pricing if you want accurate cost estimates.
DEFAULT_PRICING: dict[str, TokenPricing] = {
    # Sensible defaults (edit as needed)
    "gpt-4o": TokenPricing(input_per_million=5.0, output_per_million=15.0),
    "gpt-4o-mini": TokenPricing(input_per_million=0.15, output_per_million=0.60),
}


def estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    pricing: Optional[dict[str, TokenPricing]] = None,
) -> Optional[float]:
    if prompt_tokens is None and completion_tokens is None:
        return None

    p = (pricing or DEFAULT_PRICING).get(model)
    if not p:
        return None

    in_tok = float(prompt_tokens or 0)
    out_tok = float(completion_tokens or 0)

    # cost = (tokens / 1_000_000) * price_per_million
    return (in_tok / 1_000_000.0) * p.input_per_million + (out_tok / 1_000_000.0) * p.output_per_million

