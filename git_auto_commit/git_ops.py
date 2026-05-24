import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .models import AppConfig, RepoConfig, RepoState, ScanResult

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}
TIMEOUT = 60
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class GitError(Exception):
    pass


class GitNotFoundError(GitError):
    pass


class NotAGitRepoError(GitError):
    pass


class DetachedHeadError(GitError):
    pass


class CommitFailedError(GitError):
    pass


class PushFailedError(GitError):
    pass


def _run_git(path: Path, args: list[str], timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            encoding="utf-8",
            timeout=timeout,
            env={**subprocess.os.environ, **GIT_ENV},
            creationflags=CREATION_FLAGS,
        )
    except FileNotFoundError:
        raise GitNotFoundError("Git 未安装或不在 PATH 中")


def check_git_installed() -> None:
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            creationflags=CREATION_FLAGS,
        )
    except FileNotFoundError:
        raise GitNotFoundError("Git 未安装或不在 PATH 中，请先安装 Git。")


def is_git_repo(path: Path) -> bool:
    result = _run_git(path, ["rev-parse", "--git-dir"])
    return result.returncode == 0


def has_changes(path: Path) -> bool:
    result = _run_git(path, ["status", "--porcelain"])
    return bool(result.stdout.strip())


def has_remote(path: Path) -> bool:
    result = _run_git(path, ["remote"])
    return bool(result.stdout.strip())


def is_detached_head(path: Path) -> bool:
    result = _run_git(path, ["symbolic-ref", "-q", "HEAD"])
    return result.returncode != 0


def get_current_branch(path: Path) -> str:
    if is_detached_head(path):
        return "HEAD (detached)"
    result = _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def has_index_lock(path: Path) -> bool:
    lock_file = path / ".git" / "index.lock"
    return lock_file.exists()


def add_all(path: Path) -> None:
    result = _run_git(path, ["add", "-A"])
    if result.returncode != 0:
        raise GitError(f"git add 失败: {result.stderr.strip()}")


def commit(path: Path, message: str, allow_empty: bool = False) -> str:
    args = ["commit", "-m", message]
    if allow_empty:
        args.insert(1, "--allow-empty")
    result = _run_git(path, args)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Please tell me who you are" in stderr:
            raise CommitFailedError(
                "Git 用户未配置，请执行: git config --global user.name / user.email"
            )
        if "nothing to commit" in stderr and not allow_empty:
            raise CommitFailedError("没有可提交的内容（并发竞争）")
        raise CommitFailedError(f"git commit 失败: {stderr}")
    rev_result = _run_git(path, ["rev-parse", "--short", "HEAD"])
    return rev_result.stdout.strip()


def pull(path: Path) -> bool:
    result = _run_git(path, ["pull", "--ff-only"])
    return result.returncode == 0


def push(path: Path) -> bool:
    result = _run_git(path, ["push"])
    return result.returncode == 0


def push_with_retry(path: Path, max_retries: int, delay: int, logger: logging.Logger) -> bool:
    for attempt in range(1, max_retries + 1):
        if push(path):
            return True
        if attempt < max_retries:
            logger.warning("Push 第 %d/%d 次失败，%d 秒后重试...", attempt, max_retries, delay)
            time.sleep(delay)
    return False


def process_repo(
    repo: RepoConfig,
    app_config: AppConfig,
    logger: logging.Logger,
    dry_run: bool = False,
    force: bool = False,
) -> ScanResult:
    path = repo.path
    repo_name = path.name
    action_label = "一键推送" if force else ""

    if not path.exists():
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message="路径不存在",
        )

    if not is_git_repo(path):
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message="不是一个 Git 仓库",
        )

    if not repo.enabled:
        return ScanResult(repo_path=path, state=RepoState.SKIPPED)

    if has_index_lock(path):
        logger.warning("[%s] 存在 .git/index.lock 文件，跳过本轮扫描。", repo_name)
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=".git/index.lock 存在（残留锁文件）",
        )

    is_detached = is_detached_head(path)
    if is_detached:
        logger.warning("[%s] 处于 Detached HEAD 状态，将提交但跳过 push。", repo_name)

    has_changes_flag = has_changes(path)
    if not force and not has_changes_flag:
        logger.info("[%s] 没有变更。", repo_name)
        return ScanResult(repo_path=path, state=RepoState.CLEAN)

    if force:
        logger.info("[%s] [一键推送] 强制执行 add + commit + push。", repo_name)
    else:
        logger.info("[%s] 检测到变更。", repo_name)

    if dry_run:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{repo.commit_message_prefix}scheduled commit [{ts}]"
        logger.info("[%s] [预览模式] 将 add 所有文件并 commit: %s", repo_name, msg)
        if not is_detached and has_remote(path):
            logger.info("[%s] [预览模式] 将执行 push。", repo_name)
        return ScanResult(
            repo_path=path,
            state=RepoState.DIRTY,
            commit_hash="DRY_RUN",
            push_success=None,
        )

    remote = has_remote(path)
    if app_config.pull_before_push and remote and not is_detached:
        logger.info("[%s] 拉取最新代码...", repo_name)
        if pull(path):
            logger.info("[%s] 拉取成功。", repo_name)
        else:
            logger.warning("[%s] 拉取失败（非快进或网络问题），继续执行。", repo_name)

    try:
        logger.info("[%s] 暂存所有变更...", repo_name)
        add_all(path)
    except GitError as e:
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=str(e),
        )

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "一键推送: " if force else repo.commit_message_prefix
    message = f"{prefix}scheduled commit [{ts}]"
    logger.info("[%s] 提交: %s", repo_name, message)

    try:
        commit_hash = commit(path, message, allow_empty=force)
    except CommitFailedError as e:
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=str(e),
        )

    logger.info("[%s] 已提交 %s。", repo_name, commit_hash)

    push_ok = None
    if remote and not is_detached:
        logger.info("[%s] 推送中...", repo_name)
        push_ok = push_with_retry(
            path,
            app_config.max_push_retries,
            app_config.push_retry_delay_seconds,
            logger,
        )
        if push_ok:
            logger.info("[%s] 推送成功。", repo_name)
        else:
            logger.error("[%s] 推送失败（重试 %d 次后放弃），提交仅保留在本地。", repo_name, app_config.max_push_retries)
    elif is_detached:
        logger.info("[%s] 跳过推送（Detached HEAD）。", repo_name)
    elif not remote:
        logger.info("[%s] 没有远程仓库，跳过推送。", repo_name)

    return ScanResult(
        repo_path=path,
        state=RepoState.DIRTY,
        commit_hash=commit_hash,
        push_success=push_ok,
    )
