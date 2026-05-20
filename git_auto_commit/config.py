import json
import logging
from pathlib import Path

from .models import AppConfig, RepoConfig


def _resolve_path(path_str: str) -> Path:
    p = Path(path_str)
    if str(p).startswith("~"):
        p = p.expanduser()
    return p.resolve()


def load_config(config_path: Path, logger: logging.Logger) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")

    if "repos" not in data:
        raise ValueError("Config must contain a 'repos' field")

    repos = []
    seen_paths: set[Path] = set()

    for i, entry in enumerate(data["repos"]):
        if not isinstance(entry, dict) or "path" not in entry:
            logger.warning("Repo entry #%d missing 'path' field. Skipping.", i + 1)
            continue

        path = _resolve_path(entry["path"])
        if path in seen_paths:
            logger.warning("Duplicate repo path: %s. Skipping.", path)
            continue
        seen_paths.add(path)

        repos.append(RepoConfig(
            path=path,
            enabled=entry.get("enabled", True),
            commit_message_prefix=entry.get("commit_message_prefix", "auto: "),
        ))

    if not repos:
        raise ValueError("No valid repo entries found in config")

    config = AppConfig(
        repos=repos,
        interval_minutes=data.get("interval_minutes", 30),
        pull_before_push=data.get("pull_before_push", True),
        max_push_retries=data.get("max_push_retries", 3),
        push_retry_delay_seconds=data.get("push_retry_delay_seconds", 5),
    )

    for repo in config.repos:
        if not repo.path.exists():
            logger.warning("Repo path does not exist: %s", repo.path)
        elif not repo.path.is_dir():
            logger.warning("Repo path is not a directory: %s", repo.path)

    logger.info("Loaded %d repos from config. Interval: %d min.", len(config.repos), config.interval_minutes)
    return config
