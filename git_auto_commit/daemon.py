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
        print("\n强制退出！", file=sys.stderr)
        sys.exit(1)
    _shutdown_requested = True
    print("\n收到关闭信号，正在完成当前操作..."
          "再次按 Ctrl+C 强制退出。", file=sys.stderr)


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
    logger.info("本轮扫描汇总：")
    for r in results:
        icon = _status_icon(r)
        name = r.repo_path.name
        if r.state == RepoState.DIRTY:
            extra = f"  commit={r.commit_hash}"
            if r.push_success:
                extra += "  已推送"
            elif r.push_success is False:
                extra += "  推送失败"
            else:
                extra += "  未推送"
        elif r.state == RepoState.ERROR:
            extra = f"  {r.error_message}"
        elif r.state == RepoState.SKIPPED:
            extra = "  已禁用"
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
    logger.info("开始扫描，共 %d 个仓库。", len(enabled_repos))
    logger.info("=" * 50)

    for repo in config.repos:
        global _shutdown_requested
        if _shutdown_requested:
            logger.info("收到关闭信号，停止扫描。")
            break

        if not repo.enabled:
            logger.info("[%s] 已禁用，跳过。", repo.path.name)
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
    port: int = 8080,
    no_web: bool = False,
    config_path: Path | None = None,
) -> None:
    global _shutdown_requested, _force_quit
    from .web import SharedState, start_web_server

    _register_handlers()

    state = SharedState(config, config_path=config_path)

    server = None
    if not no_web:
        server = start_web_server(port, state, config_path=config_path)
        logger.info("Web 管理面板: http://localhost:%d", port)
    else:
        logger.info("Web 管理面板已禁用。")

    logger.info("Git 自动提交工具已启动。")
    logger.info("间隔: %d 分钟  |  仓库数: %d  |  预览模式: %s",
                config.interval_minutes, len(config.repos), dry_run)
    logger.info("按 Ctrl+C 停止。")
    logger.info("")

    _cycle_running = False

    def _do_scan() -> None:
        nonlocal _cycle_running
        if _cycle_running:
            return
        _cycle_running = True
        state.scanning = True
        try:
            results = run_scan_cycle(config, logger, dry_run=dry_run)
            with state._lock:
                state.last_results = results
                state.add_history(results)
        except Exception:
            logger.exception("扫描过程中发生未知错误。")
        finally:
            _cycle_running = False
            state.scanning = False

    try:
        while True:
            if _shutdown_requested:
                break

            triggered = False
            with state._lock:
                if state._trigger_scan:
                    state._trigger_scan = False
                    triggered = True

            if triggered:
                logger.info("收到手动触发扫描请求。")
                _do_scan()
            elif not _cycle_running:
                _do_scan()

            if once:
                break

            if _shutdown_requested:
                break

            next_time = datetime.now() + timedelta(minutes=config.interval_minutes)
            state.next_scan_time = next_time
            logger.info("下次扫描: %d 分钟后，约 %s。",
                        config.interval_minutes, next_time.strftime("%H:%M:%S"))

            # Sleep 1s at a time, checking for trigger and shutdown
            for _ in range(config.interval_minutes * 60):
                if _shutdown_requested:
                    break
                with state._lock:
                    if state._trigger_scan:
                        break
                time.sleep(1)

    except KeyboardInterrupt:
        pass

    if server:
        server.shutdown()

    if _force_quit:
        logger.info("已强制退出。")
    else:
        logger.info("守护进程已停止。")
