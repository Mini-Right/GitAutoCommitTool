from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path


class RepoState(Enum):
    CLEAN = auto()
    DIRTY = auto()
    ERROR = auto()
    SKIPPED = auto()


@dataclass
class RepoConfig:
    path: Path
    enabled: bool = True
    commit_message_prefix: str = "自动提交: "


@dataclass
class AppConfig:
    repos: list[RepoConfig]
    interval_minutes: int = 30
    pull_before_push: bool = True
    max_push_retries: int = 3
    push_retry_delay_seconds: int = 5


@dataclass
class ScanResult:
    repo_path: Path
    state: RepoState
    commit_hash: str | None = None
    push_success: bool | None = None
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
