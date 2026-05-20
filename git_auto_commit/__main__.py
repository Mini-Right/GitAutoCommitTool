import logging
import sys

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

    try:
        check_git_installed()
    except GitNotFoundError as e:
        logger.critical(str(e))
        sys.exit(1)

    try:
        config = load_config(args.config.resolve(), logger)
    except (FileNotFoundError, ValueError) as e:
        logger.critical(str(e))
        sys.exit(1)

    if args.interval is not None:
        config.interval_minutes = args.interval

    daemon_loop(config, logger, dry_run=args.dry_run, once=args.once)


if __name__ == "__main__":
    main()
