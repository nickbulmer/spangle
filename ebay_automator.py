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


def main() -> int:
    load_dotenv()

    # Local folder-per-product root (relative by default)
    products_root = Path(os.getenv("PRODUCTS_ROOT", "products"))
    watch = os.getenv("WATCH_PRODUCTS", "false").lower() == "true"
    interval = int(os.getenv("WATCH_INTERVAL_SECONDS", "10"))

    # folder_automator will validate OPENAI_API_KEY
    folder_automator.process_products_root(products_root, watch=watch, interval_seconds=interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

