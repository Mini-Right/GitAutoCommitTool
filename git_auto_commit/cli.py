import argparse
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="git-auto-commit",
        description="Automatically commit and push changes in configured git repositories.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to config JSON (default: ./config.json)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Minutes between scans (overrides config value)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually committing or pushing",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan cycle and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show warnings and errors",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Write logs to a file",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output",
    )
    return parser.parse_args(argv)
