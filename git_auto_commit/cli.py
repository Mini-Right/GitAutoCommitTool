import argparse
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="git-auto-commit",
        description="自动对配置的 Git 仓库进行提交和推送。",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="配置文件路径（默认: ./config.json）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="扫描间隔分钟数（覆盖配置文件中的值）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅展示将要执行的操作，不实际提交或推送",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅执行一次扫描后退出",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用调试级别日志",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="仅显示警告和错误",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="将日志写入文件",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用终端彩色输出",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web 管理面板端口（默认: 8080）",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="禁用 Web 管理面板，仅 CLI 模式",
    )
    return parser.parse_args(argv)
