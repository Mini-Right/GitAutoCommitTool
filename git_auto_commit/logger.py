import logging
import sys
from datetime import datetime
from pathlib import Path

SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")

COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[0m",
    "SUCCESS": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m",
}
RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def __init__(self, use_colors: bool = True):
        super().__init__("%(asctime)s [%(levelname)-8s] %(message)s", "%H:%M:%S")
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            level = record.levelname
            color = COLORS.get(level, "")
            record.levelname = f"{color}{level}{RESET}"
            record.msg = f"{color}{record.msg}{RESET}"
            record.asctime = f"{color}{self.formatTime(record, self.datefmt)}{RESET}"
        return super().format(record)


class PlainFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s [%(levelname)-8s] %(message)s", "%Y-%m-%d %H:%M:%S")


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    use_colors: bool = True,
) -> logging.Logger:
    logger = logging.getLogger("git_auto_commit")
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(use_colors))
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(PlainFormatter())
        logger.addHandler(file_handler)

    return logger


def log_success(logger: logging.Logger, msg: str, *args, **kwargs) -> None:
    logger.log(SUCCESS, msg, *args, **kwargs)
