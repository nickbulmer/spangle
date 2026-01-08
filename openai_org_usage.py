from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


class OpenAIUsageAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIIdentity:
    user: dict[str, Any]
    organizations: list[dict[str, Any]]


@dataclass(frozen=True)
class OpenAIUsageSummary:
    start_time: int
    end_time: int
    total_cost_usd: Optional[float]
    total_input_tokens: Optional[int]
    total_output_tokens: Optional[int]
    total_tokens: Optional[int]


def _pick_key() -> str:
    # Per docs, org endpoints often require an admin key.
    return os.getenv("ADMIN_OPENAI_API_KEY") or ""


def _headers() -> dict[str, str]:
    key = _pick_key()
    if not key:
        raise OpenAIUsageAPIError(
            "ADMIN_OPENAI_API_KEY is not set (required for org usage/costs)."
        )
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    org = os.getenv("OPENAI_ORGANIZATION")
    proj = os.getenv("OPENAI_PROJECT")
    if org:
        h["OpenAI-Organization"] = org
    if proj:
        h["OpenAI-Project"] = proj
    return h


def _get(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    if r.status_code >= 400:
        raise OpenAIUsageAPIError(f"{r.status_code} {r.text}")
    return r.json()


def me() -> OpenAIIdentity:
    data = _get("https://api.openai.com/v1/me")
    orgs = data.get("organizations") or data.get("orgs") or []
    return OpenAIIdentity(user=data.get("user") or {}, organizations=orgs)


def _sum_cost_buckets(costs_json: dict[str, Any]) -> Optional[float]:
    # The Costs endpoint returns bucketed results; sum 'amount.value' if present.
    total = 0.0
    found = False
    for b in costs_json.get("data") or []:
        for res in b.get("results") or []:
            amt = res.get("amount") or {}
            val = amt.get("value")
            if val is None:
                continue
            total += float(val)
            found = True
    return total if found else None


def _sum_usage_buckets(usage_json: dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    # Best-effort: sum input_tokens + output_tokens if present.
    in_total = 0
    out_total = 0
    found = False
    for b in usage_json.get("data") or []:
        for res in b.get("results") or []:
            inp = res.get("input_tokens")
            outp = res.get("output_tokens")
            if inp is not None:
                in_total += int(inp)
                found = True
            if outp is not None:
                out_total += int(outp)
                found = True
    if not found:
        return None, None
    return in_total, out_total


def usage_and_costs(*, days: int = 30) -> OpenAIUsageSummary:
    end_time = int(time.time())
    start_time = end_time - int(days) * 86400

    # Costs (org-level)
    costs = _get(
        "https://api.openai.com/v1/organization/costs",
        params={"start_time": start_time, "end_time": end_time, "bucket_width": "1d"},
    )
    total_cost = _sum_cost_buckets(costs)

    # Usage (completions) - aligns with doc in USING_OPEN_AI.md
    usage = _get(
        "https://api.openai.com/v1/organization/usage/completions",
        params={"start_time": start_time, "end_time": end_time, "bucket_width": "1d"},
    )
    in_tok, out_tok = _sum_usage_buckets(usage)

    total_tokens = None
    if in_tok is not None or out_tok is not None:
        total_tokens = int((in_tok or 0) + (out_tok or 0))

    return OpenAIUsageSummary(
        start_time=start_time,
        end_time=end_time,
        total_cost_usd=total_cost,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        total_tokens=total_tokens,
    )

