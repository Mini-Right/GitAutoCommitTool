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
        default_config = {
            "repos": [],
            "interval_minutes": 30,
            "pull_before_push": False,
            "max_push_retries": 3,
            "push_retry_delay_seconds": 5,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        logger.info("已创建默认配置文件: %s，请编辑 repos 列表添加仓库路径。", config_path)
        return AppConfig(repos=[])

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 JSON 格式无效: {e}")

    if "repos" not in data:
        raise ValueError("配置文件中必须包含 'repos' 字段")

    repos = []
    seen_paths: set[Path] = set()

    for i, entry in enumerate(data["repos"]):
        if not isinstance(entry, dict) or "path" not in entry:
            logger.warning("第 %d 个仓库条目缺少 'path' 字段，跳过。", i + 1)
            continue

        path = _resolve_path(entry["path"])
        if path in seen_paths:
            logger.warning("仓库路径重复: %s，跳过。", path)
            continue
        seen_paths.add(path)

        repos.append(RepoConfig(
            path=path,
            enabled=entry.get("enabled", True),
            commit_message_prefix=entry.get("commit_message_prefix", "自动提交: "),
        ))

    if not repos:
        logger.warning("仓库列表为空，请通过 Web 管理面板或配置文件添加仓库。")

    config = AppConfig(
        repos=repos,
        interval_minutes=data.get("interval_minutes", 30),
        pull_before_push=data.get("pull_before_push", True),
        max_push_retries=data.get("max_push_retries", 3),
        push_retry_delay_seconds=data.get("push_retry_delay_seconds", 5),
    )

    for repo in config.repos:
        if not repo.path.exists():
            logger.warning("仓库路径不存在: %s", repo.path)
        elif not repo.path.is_dir():
            logger.warning("仓库路径不是目录: %s", repo.path)

    logger.info("已加载 %d 个仓库，扫描间隔: %d 分钟。", len(config.repos), config.interval_minutes)
    return config
