import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .models import AppConfig, RepoConfig, RepoState, ScanResult

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}
TIMEOUT = 60


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
            text=True,
            timeout=timeout,
            env={**subprocess.os.environ, **GIT_ENV},
        )
    except FileNotFoundError:
        raise GitNotFoundError("git is not installed or not on PATH")


def check_git_installed() -> None:
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise GitNotFoundError("git is not installed or not on PATH. Please install git first.")


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
        raise GitError(f"git add failed: {result.stderr.strip()}")


def commit(path: Path, message: str) -> str:
    result = _run_git(path, ["commit", "-m", message])
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Please tell me who you are" in stderr:
            raise CommitFailedError(
                "Git user not configured. Run: git config --global user.name / user.email"
            )
        if "nothing to commit" in stderr:
            raise CommitFailedError("Nothing to commit (race condition)")
        raise CommitFailedError(f"git commit failed: {stderr}")
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
            logger.warning("Push attempt %d/%d failed. Retrying in %ds...", attempt, max_retries, delay)
            time.sleep(delay)
    return False


def process_repo(
    repo: RepoConfig,
    app_config: AppConfig,
    logger: logging.Logger,
    dry_run: bool = False,
) -> ScanResult:
    path = repo.path
    repo_name = path.name

    if not path.exists():
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message="Path does not exist",
        )

    if not is_git_repo(path):
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message="Not a git repository",
        )

    if not repo.enabled:
        return ScanResult(repo_path=path, state=RepoState.SKIPPED)

    if has_index_lock(path):
        logger.warning("[%s] .git/index.lock exists. Skipping this cycle.", repo_name)
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=".git/index.lock exists — stale lock file",
        )

    is_detached = is_detached_head(path)
    if is_detached:
        logger.warning("[%s] Detached HEAD. Will commit but skip push.", repo_name)

    if not has_changes(path):
        logger.info("[%s] No changes.", repo_name)
        return ScanResult(repo_path=path, state=RepoState.CLEAN)

    logger.info("[%s] Changes detected.", repo_name)

    if dry_run:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{repo.commit_message_prefix}scheduled commit [{ts}]"
        logger.info("[%s] [DRY RUN] Would add all & commit with: %s", repo_name, msg)
        if not is_detached and has_remote(path):
            logger.info("[%s] [DRY RUN] Would push.", repo_name)
        return ScanResult(
            repo_path=path,
            state=RepoState.DIRTY,
            commit_hash="DRY_RUN",
            push_success=None,
        )

    remote = has_remote(path)
    if app_config.pull_before_push and remote and not is_detached:
        logger.info("[%s] Pulling latest changes...", repo_name)
        if pull(path):
            logger.info("[%s] Pull successful.", repo_name)
        else:
            logger.warning("[%s] Pull failed (non-fast-forward or network issue). Continuing anyway.", repo_name)

    try:
        logger.info("[%s] Staging all changes...", repo_name)
        add_all(path)
    except GitError as e:
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=str(e),
        )

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{repo.commit_message_prefix}scheduled commit [{ts}]"
    logger.info("[%s] Committing: %s", repo_name, message)

    try:
        commit_hash = commit(path, message)
    except CommitFailedError as e:
        return ScanResult(
            repo_path=path,
            state=RepoState.ERROR,
            error_message=str(e),
        )

    logger.info("[%s] Committed %s.", repo_name, commit_hash)

    push_ok = None
    if remote and not is_detached:
        logger.info("[%s] Pushing...", repo_name)
        push_ok = push_with_retry(
            path,
            app_config.max_push_retries,
            app_config.push_retry_delay_seconds,
            logger,
        )
        if push_ok:
            logger.info("[%s] Push successful.", repo_name)
        else:
            logger.error("[%s] Push failed after %d retries. Commit is local only.", repo_name, app_config.max_push_retries)
    elif is_detached:
        logger.info("[%s] Skipping push (detached HEAD).", repo_name)
    elif not remote:
        logger.info("[%s] No remote configured. Skipping push.", repo_name)

    return ScanResult(
        repo_path=path,
        state=RepoState.DIRTY,
        commit_hash=commit_hash,
        push_success=push_ok,
    )
