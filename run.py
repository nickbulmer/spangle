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


def main() -> int:
    load_dotenv()

    # Local folder-per-product root (relative by default)
    products_root = Path(os.getenv("PRODUCTS_ROOT", "products"))
    watch = os.getenv("WATCH_PRODUCTS", "false").lower() == "true"
    interval = int(os.getenv("WATCH_INTERVAL_SECONDS", "10"))

    # Print local OpenAI usage/cost summary every run (best-effort; costs are estimates)
    try:
        db_path = os.getenv("EBAY_DB_PATH", "ebay_data.db")
        conn = database.connect(db_path)
        database.init_db(conn)
        days = int(os.getenv("OPENAI_USAGE_DAYS", "30"))
        before = database.openai_usage_summary(conn, days=days)
        print()
        print("=" * 60)
        print(f"OpenAI usage (local estimate) - last {days} days")
        print("=" * 60)
        print(
            f"Calls: {before['calls']}  Tokens: {before['total_tokens']}  "
            f"Est. cost (USD): {before['estimated_cost_usd']:.6f}"
        )
        print("=" * 60)
        print()
        conn.close()
    except Exception:
        # Never block the main workflow on usage reporting
        pass

    # folder_automator will validate OPENAI_API_KEY
    folder_automator.process_products_root(products_root, watch=watch, interval_seconds=interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

