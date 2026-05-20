import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import AppConfig
from .git_ops import process_repo
from .logger import log_success
from .models import RepoState, ScanResult

_shutdown_requested = False
_force_quit = False


def _signal_handler(signum: int, frame: object) -> None:
    global _shutdown_requested, _force_quit
    if _force_quit or _shutdown_requested:
        _force_quit = True
        print("\nForce quitting!", file=sys.stderr)
        sys.exit(1)
    _shutdown_requested = True
    print("\nShutdown requested. Completing current operation... "
          "Press Ctrl+C again to force quit.", file=sys.stderr)


def _register_handlers() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)


def _status_icon(result: ScanResult) -> str:
    if result.state == RepoState.DIRTY:
        if result.push_success:
            return "OK"
        elif result.push_success is False:
            return "LOCAL"
        return "NO_PUSH"
    elif result.state == RepoState.CLEAN:
        return "---"
    elif result.state == RepoState.SKIPPED:
        return "SKIP"
    return "ERR"


def _print_summary(results: list[ScanResult], logger: logging.Logger) -> None:
    logger.info("=" * 50)
    logger.info("Cycle summary:")
    for r in results:
        icon = _status_icon(r)
        name = r.repo_path.name
        if r.state == RepoState.DIRTY:
            extra = f"  commit={r.commit_hash}"
            if r.push_success:
                extra += "  pushed"
            elif r.push_success is False:
                extra += "  push_failed"
            else:
                extra += "  no_push"
        elif r.state == RepoState.ERROR:
            extra = f"  {r.error_message}"
        elif r.state == RepoState.SKIPPED:
            extra = "  disabled"
        else:
            extra = ""
        logger.info("  %-30s %-5s%s", name, icon, extra)
    logger.info("=" * 50)


def run_scan_cycle(
    config: AppConfig,
    logger: logging.Logger,
    dry_run: bool = False,
) -> list[ScanResult]:
    results: list[ScanResult] = []
    enabled_repos = [r for r in config.repos if r.enabled]

    logger.info("=" * 50)
    logger.info("Scan cycle starting. %d repos to check.", len(enabled_repos))
    logger.info("=" * 50)

    for repo in config.repos:
        global _shutdown_requested
        if _shutdown_requested:
            logger.info("Shutdown requested. Stopping scan cycle.")
            break

        if not repo.enabled:
            logger.info("[%s] Disabled. Skipping.", repo.path.name)
            results.append(ScanResult(repo_path=repo.path, state=RepoState.SKIPPED))
            continue

        result = process_repo(repo, config, logger, dry_run=dry_run)
        results.append(result)

    if results:
        _print_summary(results, logger)

    return results


def daemon_loop(
    config: AppConfig,
    logger: logging.Logger,
    dry_run: bool = False,
    once: bool = False,
) -> None:
    global _shutdown_requested, _force_quit
    _register_handlers()

    logger.info("Git Auto Commit Tool started.")
    logger.info("Interval: %d min  |  Repos: %d  |  Dry-run: %s",
                config.interval_minutes, len(config.repos), dry_run)
    logger.info("Press Ctrl+C to stop.")
    logger.info("")

    _cycle_running = False

    try:
        while True:
            if _shutdown_requested:
                break

            if _cycle_running:
                logger.warning("Previous scan cycle still running. Skipping this interval.")
            else:
                _cycle_running = True
                try:
                    run_scan_cycle(config, logger, dry_run=dry_run)
                except Exception:
                    logger.exception("Unexpected error during scan cycle.")
                finally:
                    _cycle_running = False

            if once:
                break

            if _shutdown_requested:
                break

            next_time = datetime.now() + timedelta(minutes=config.interval_minutes)
            logger.info("Next scan in %d minutes at %s.",
                        config.interval_minutes, next_time.strftime("%H:%M:%S"))

            for _ in range(config.interval_minutes * 60):
                if _shutdown_requested:
                    break
                time.sleep(1)

    except KeyboardInterrupt:
        pass

    if _force_quit:
        logger.info("Force quit.")
    else:
        logger.info("Daemon stopped.")
