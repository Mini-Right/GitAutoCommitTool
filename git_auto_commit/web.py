import json
import logging
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .git_ops import process_repo
from .models import AppConfig, RepoConfig, RepoState, ScanResult

# Handle PyInstaller frozen builds
if getattr(sys, "frozen", False):
    STATIC_DIR = Path(sys._MEIPASS) / "git_auto_commit" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"

HISTORY_MAX = 50


LOG_BUFFER_SIZE = 200


class LogHandler(logging.Handler):
    def __init__(self, buffer: list[dict]):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": record.levelname,
            "msg": self.format(record),
        }
        self.buffer.append(entry)
        if len(self.buffer) > LOG_BUFFER_SIZE:
            self.buffer[:] = self.buffer[-LOG_BUFFER_SIZE:]


class SharedState:
    def __init__(self, config: AppConfig, config_path: Path | None = None):
        self.config = config
        self.config_path = config_path
        self.last_results: list[ScanResult] = []
        self.next_scan_time: datetime | None = None
        self.history: list[list[ScanResult]] = []
        self.scanning: bool = False
        self._trigger_scan: bool = False
        self._force_push: bool = False
        self._log_buffer: list[dict] = []
        self._log_index: int = 0
        self._lock = threading.Lock()

    def acquire(self):
        self._lock.acquire()

    def release(self):
        self._lock.release()

    def add_history(self, results: list[ScanResult]) -> None:
        self.history.append(results)
        if len(self.history) > HISTORY_MAX:
            self.history = self.history[-HISTORY_MAX:]


def _repo_to_dict(repo: RepoConfig, result: ScanResult | None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": repo.path.name,
        "path": str(repo.path),
        "enabled": repo.enabled,
        "prefix": repo.commit_message_prefix,
    }
    if result:
        d["state"] = result.state.name
        d["commit_hash"] = result.commit_hash
        d["push_success"] = result.push_success
        d["error_message"] = result.error_message
        d["timestamp"] = result.timestamp.strftime("%H:%M:%S")
    else:
        d["state"] = "UNKNOWN"
        d["commit_hash"] = None
        d["push_success"] = None
        d["error_message"] = None
        d["timestamp"] = None
    return d


def _build_status(state: SharedState) -> dict[str, Any]:
    result_map: dict[Path, ScanResult] = {}
    for r in state.last_results:
        result_map[r.repo_path] = r

    return {
        "running": True,
        "scanning": state.scanning,
        "interval_minutes": state.config.interval_minutes,
        "next_scan_time": state.next_scan_time.strftime("%H:%M:%S") if state.next_scan_time else None,
        "dry_run": False,
        "repos": [_repo_to_dict(r, result_map.get(r.path)) for r in state.config.repos],
    }


class _RequestHandler(BaseHTTPRequestHandler):
    shared_state: SharedState

    def log_message(self, fmt: str, *args: Any) -> None:
        pass  # suppress access logs

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, path: str) -> None:
        if path == "/" or path == "":
            path = "/index.html"
        file_path = STATIC_DIR / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content = file_path.read_bytes()
        self.send_response(200)
        if file_path.suffix == ".html":
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif file_path.suffix == ".js":
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
        elif file_path.suffix == ".css":
            self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if self.path == "/api/status":
            with self.shared_state._lock:
                data = _build_status(self.shared_state)
            self._send_json(data)
        elif self.path == "/api/config":
            with self.shared_state._lock:
                repos = []
                for r in self.shared_state.config.repos:
                    repos.append({
                        "path": str(r.path),
                        "enabled": r.enabled,
                        "commit_message_prefix": r.commit_message_prefix,
                    })
                data = {
                    "repos": repos,
                    "interval_minutes": self.shared_state.config.interval_minutes,
                    "pull_before_push": self.shared_state.config.pull_before_push,
                    "max_push_retries": self.shared_state.config.max_push_retries,
                    "push_retry_delay_seconds": self.shared_state.config.push_retry_delay_seconds,
                }
            self._send_json(data)
        elif self.path == "/api/history":
            with self.shared_state._lock:
                history_data = []
                for cycle in self.shared_state.history:
                    cycle_data = []
                    for r in cycle:
                        cycle_data.append({
                            "name": r.repo_path.name,
                            "path": str(r.repo_path),
                            "state": r.state.name,
                            "commit_hash": r.commit_hash,
                            "push_success": r.push_success,
                            "error_message": r.error_message,
                            "timestamp": r.timestamp.strftime("%H:%M:%S"),
                        })
                    history_data.append(cycle_data)
            self._send_json(history_data)
        elif self.path.startswith("/api/logs"):
            with self.shared_state._lock:
                buf = self.shared_state._log_buffer
                # Return logs since the given index
                since = 0
                if "?since=" in self.path:
                    try:
                        since = int(self.path.split("?since=")[1])
                    except ValueError:
                        pass
                logs = buf[since:]
                self._send_json({"logs": logs, "index": len(buf)})
        else:
            self._serve_static(self.path)

    def do_POST(self) -> None:
        if self.path == "/api/scan":
            with self.shared_state._lock:
                self.shared_state._trigger_scan = True
            self._send_json({"ok": True, "message": "扫描已触发"})
        elif self.path == "/api/push-all":
            with self.shared_state._lock:
                self.shared_state._trigger_scan = True
                self.shared_state._force_push = True
            self._send_json({"ok": True, "message": "一键推送已触发，将对所有仓库执行 add + commit + push"})
        elif self.path == "/api/repos/push":
            body = self._read_body()
            path_str = body.get("path", "")
            if not path_str:
                self._send_json({"ok": False, "message": "缺少 path 字段"}, 400)
                return
            target = Path(path_str).resolve()
            repo_config = None
            with self.shared_state._lock:
                for r in self.shared_state.config.repos:
                    if r.path == target:
                        repo_config = r
                        break
            if repo_config is None:
                self._send_json({"ok": False, "message": "仓库不存在"}, 404)
                return
            logger = logging.getLogger("git_auto_commit")
            result = process_repo(repo_config, self.shared_state.config, logger, dry_run=False, force=True)
            with self.shared_state._lock:
                updated = False
                for i, r in enumerate(self.shared_state.last_results):
                    if r.repo_path == target:
                        self.shared_state.last_results[i] = result
                        updated = True
                        break
                if not updated:
                    self.shared_state.last_results.append(result)
            self._send_json({
                "ok": result.state != RepoState.ERROR,
                "message": "推送完成" if result.state == RepoState.DIRTY else (result.error_message or "推送失败"),
                "state": result.state.name,
                "commit_hash": result.commit_hash,
                "push_success": result.push_success,
            })
        elif self.path == "/api/repos":
            body = self._read_body()
            path_str = body.get("path", "")
            if not path_str:
                self._send_json({"ok": False, "message": "缺少 path 字段"}, 400)
                return
            new_path = Path(path_str).resolve()
            with self.shared_state._lock:
                for r in self.shared_state.config.repos:
                    if r.path == new_path:
                        self._send_json({"ok": False, "message": "仓库路径已存在"}, 400)
                        return
                new_repo = RepoConfig(
                    path=new_path,
                    enabled=body.get("enabled", True),
                    commit_message_prefix=body.get("commit_message_prefix", "自动提交: "),
                )
                self.shared_state.config.repos.append(new_repo)
            self._save_config(self.shared_state.config)
            self._send_json({"ok": True, "message": "仓库已添加"})
        else:
            self._send_json({"ok": False, "message": "Not found"}, 404)

    def do_PUT(self) -> None:
        if self.path == "/api/repos":
            body = self._read_body()
            path_str = body.get("path", "")
            if not path_str:
                self._send_json({"ok": False, "message": "缺少 path 字段"}, 400)
                return
            target = Path(path_str).resolve()
            with self.shared_state._lock:
                for r in self.shared_state.config.repos:
                    if r.path == target:
                        if "enabled" in body:
                            r.enabled = bool(body["enabled"])
                        if "commit_message_prefix" in body:
                            r.commit_message_prefix = str(body["commit_message_prefix"])
                        self._save_config(self.shared_state.config)
                        self._send_json({"ok": True, "message": "仓库已更新"})
                        return
                self._send_json({"ok": False, "message": "仓库不存在"}, 404)
        elif self.path == "/api/settings":
            body = self._read_body()
            with self.shared_state._lock:
                cfg = self.shared_state.config
                if "interval_minutes" in body:
                    cfg.interval_minutes = int(body["interval_minutes"])
                if "pull_before_push" in body:
                    cfg.pull_before_push = bool(body["pull_before_push"])
                if "max_push_retries" in body:
                    cfg.max_push_retries = int(body["max_push_retries"])
                if "push_retry_delay_seconds" in body:
                    cfg.push_retry_delay_seconds = int(body["push_retry_delay_seconds"])
            self._save_config(self.shared_state.config)
            self._send_json({"ok": True, "message": "设置已更新"})
        else:
            self._send_json({"ok": False, "message": "Not found"}, 404)

    def do_DELETE(self) -> None:
        if self.path == "/api/repos":
            body = self._read_body()
            path_str = body.get("path", "")
            if not path_str:
                self._send_json({"ok": False, "message": "缺少 path 字段"}, 400)
                return
            target = Path(path_str).resolve()
            with self.shared_state._lock:
                cfg = self.shared_state.config
                for i, r in enumerate(cfg.repos):
                    if r.path == target:
                        cfg.repos.pop(i)
                        self._save_config(self.shared_state.config)
                        self._send_json({"ok": True, "message": "仓库已删除"})
                        return
                self._send_json({"ok": False, "message": "仓库不存在"}, 404)
        else:
            self._send_json({"ok": False, "message": "Not found"}, 404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _save_config(self, config: AppConfig) -> None:
        config_path = self.shared_state.config_path or Path("config.json").resolve()
        repos_data = []
        for r in config.repos:
            repos_data.append({
                "path": str(r.path),
                "enabled": r.enabled,
                "commit_message_prefix": r.commit_message_prefix,
            })
        data = {
            "repos": repos_data,
            "interval_minutes": config.interval_minutes,
            "pull_before_push": config.pull_before_push,
            "max_push_retries": config.max_push_retries,
            "push_retry_delay_seconds": config.push_retry_delay_seconds,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def start_web_server(port: int, state: SharedState, config_path: Path | None = None) -> HTTPServer:
    if config_path:
        state.config_path = config_path
    _RequestHandler.shared_state = state
    server = HTTPServer(("0.0.0.0", port), _RequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
