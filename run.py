from __future__ import annotations

"""
spangle (local-first)

This runner processes product folders from the local filesystem (ideal for Windows Google Drive sync),
and generates listing details via ChatGPT Vision.

Workflow:
  products/<product_folder>/*.jpg|png|heic...
  -> products/<product_folder>/listing.json
  -> listing_outputs/listings.csv
  -> products/<product_folder>/.processed
"""

import os
from pathlib import Path

from dotenv import load_dotenv

import folder_automator
import database
import openai_org_usage


def main() -> int:
    load_dotenv()

    # Local folder-per-product root (relative by default)
    products_root = Path(os.getenv("PRODUCTS_ROOT", "products"))
    watch = os.getenv("WATCH_PRODUCTS", "false").lower() == "true"
    interval = int(os.getenv("WATCH_INTERVAL_SECONDS", "10"))

    # Print OpenAI usage/cost summary every run.
    # Prefer OpenAI org endpoints (real costs) and fall back to local estimate if not permitted.
    try:
        db_path = os.getenv("EBAY_DB_PATH", "ebay_data.db")
        days = int(os.getenv("OPENAI_USAGE_DAYS", "30"))

        print()
        print("=" * 60)
        print(f"OpenAI usage & cost - last {days} days")
        print("=" * 60)

        try:
            api_summary = openai_org_usage.usage_and_costs(days=days)
            print("Source: OpenAI org Usage/Costs API")
            if api_summary.total_cost_usd is not None:
                print(f"Spend (USD): {api_summary.total_cost_usd:.2f}")
            else:
                print("Spend (USD): (not available)")
            if api_summary.total_tokens is not None:
                print(
                    f"Tokens: {api_summary.total_tokens} "
                    f"(input={api_summary.total_input_tokens} output={api_summary.total_output_tokens})"
                )
            else:
                print("Tokens: (not available)")
        except Exception as e:
            # Fall back to local estimate
            conn = database.connect(db_path)
            database.init_db(conn)
            before = database.openai_usage_summary(conn, days=days)
            conn.close()
            print("Source: local token log (estimate)")
            print(
                f"Calls: {before['calls']}  Tokens: {before['total_tokens']}  "
                f"Est. cost (USD): {before['estimated_cost_usd']:.6f}"
            )
            print(f"Note: API-based costs not available ({e}).")

        print()
        print("=" * 60)
        print()
    except Exception:
        # Never block the main workflow on usage reporting
        pass

    # folder_automator will validate SPANGLE_OPENAI_API_KEY
    folder_automator.process_products_root(products_root, watch=watch, interval_seconds=interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

