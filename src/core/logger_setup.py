import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 直接导入你定义的 Filter
from src.core.tracer import TraceIDFilter


def setup_logging():
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = log_dir / "app.log"

    logger = logging.getLogger()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    if logger.hasHandlers():
        logger.handlers.clear()

    # 此时不需要 [TraceID:%(trace_id)s]，因为我们要在自定义 Filter 中注入
    # 但为了兼容性，保留 %(trace_id)s 在 format 中是安全的，filter 会处理
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [TraceID:%(trace_id)s] %(message)s"
    )

    # 实例化 Filter
    trace_filter = TraceIDFilter()

    # 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(trace_filter)
    logger.addHandler(console_handler)

    # 文件 Handler
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(trace_filter)
    logger.addHandler(file_handler)

    return logger
