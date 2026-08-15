"""Backward-compatible entry point; prefer the `openfars` command."""

from openfars.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
