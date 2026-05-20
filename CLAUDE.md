# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Git Auto Commit Tool — a Python daemon that periodically scans configured Git repositories and automatically runs `git add -A` → `git commit` → `git push` when changes are detected. All log messages are in Chinese.

## Running

```bash
py -m git_auto_commit                  # Daemon mode (runs forever)
py -m git_auto_commit --once           # Single scan cycle
py -m git_auto_commit --once --dry-run # Preview without committing
py -m git_auto_commit --verbose        # Debug logging
```

Python 3.10+, stdlib only, no `pip install` required.

## Architecture

**Call chain:** `__main__.py` → parse CLI → load config → setup logger → `daemon_loop()`

**Module dependency order (bottom-up):**
1. `models.py` — dataclasses: `RepoState`, `RepoConfig`, `AppConfig`, `ScanResult`
2. `logger.py` — custom `SUCCESS` level (25), `ColoredFormatter` with ANSI codes, `setup_logging()`
3. `git_ops.py` — all Git subprocess interactions. Sole module that touches Git. `process_repo()` orchestrates the full check→pull→add→commit→push flow, **never raises** — errors are captured in `ScanResult`
4. `config.py` — loads/validates `config.json`, resolves paths, deduplicates repos
5. `cli.py` — argparse definition
6. `daemon.py` — main loop, Ctrl+C signal handling (first=graceful, second=force quit), 1-second sleep polling, cycle-overlap guard

**Key design rules:**
- One repo's failure never crashes the daemon — all per-repo errors are captured in `ScanResult`
- `git_ops._run_git()` is the single point for all `subprocess.run` calls, using `encoding="utf-8"` (not `text=True`) to avoid GBK decode errors on Chinese Windows
- `GIT_TERMINAL_PROMPT=0` is set on all Git subprocess calls to prevent hanging on credential prompts
- All subprocess calls use `timeout=60s` and `capture_output=True`
- `daemon.py` uses module-level globals `_shutdown_requested` / `_force_quit` for cross-function signal state
- Config is loaded once at startup; no hot-reload
