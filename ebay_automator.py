"""
Backwards-compatible shim.

spangle renamed the main entrypoint from `ebay_automator.py` to `run.py`.
"""

from run import main


if __name__ == "__main__":
    raise SystemExit(main())

