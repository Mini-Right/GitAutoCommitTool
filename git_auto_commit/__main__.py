import logging
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure UTF-8 output on Windows for Chinese log messages
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .cli import parse_args
from .config import load_config
from .daemon import daemon_loop
from .git_ops import GitNotFoundError, check_git_installed
from .logger import setup_logging


def main() -> None:
    args = parse_args()

    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    logger = setup_logging(
        level=level,
        log_file=args.log_file,
        use_colors=not args.no_color,
    )

    def _pause_and_exit(code: int) -> None:
        try:
            print("Press Enter to exit...", file=sys.stderr)
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        sys.exit(code)

    try:
        check_git_installed()
    except GitNotFoundError as e:
        logger.critical(str(e))
        _pause_and_exit(1)

    config_path = args.config.resolve()
    try:
        config = load_config(config_path, logger)
    except (FileNotFoundError, ValueError) as e:
        logger.critical(str(e))
        _pause_and_exit(1)

    if args.interval is not None:
        config.interval_minutes = args.interval

    if not args.no_web:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    daemon_loop(config, logger, dry_run=args.dry_run, once=args.once,
                port=args.port, no_web=args.no_web, config_path=config_path)


if __name__ == "__main__":
    main()
