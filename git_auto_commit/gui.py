import logging
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("git_auto_commit")


def _wait_for_server(url: str, timeout: int = 10) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def run_gui(port: int = 8080) -> None:
    try:
        import webview
    except ImportError:
        logger.error("pywebview 未安装，请执行: pip install pywebview")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    logger.info("正在启动管理窗口...")

    if not _wait_for_server(url):
        logger.error("Web 服务启动超时，请检查端口 %d 是否被占用。", port)
        sys.exit(1)

    window = webview.create_window(
        "Git Auto Commit - 管理面板",
        url,
        width=1100,
        height=750,
        min_size=(800, 500),
        text_select=True,
    )

    webview.start(debug=False)
    logger.info("管理窗口已关闭。")
