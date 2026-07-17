# src/worker/celery_app.py
import os

from celery import Celery
from celery.signals import after_setup_logger

from src.core.logger_setup import setup_logging

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
backend_url = os.getenv("CELERY_BACKEND_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "test_ai_worker",
    broker=broker_url,
    backend=backend_url,
    include=["src.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Singapore",
    enable_utc=True,
)


# --- 关键修改：使用 after_setup_logger 信号 ---
@after_setup_logger.connect
def on_after_setup_logger(logger, **kwargs):
    # setup_logging 内部会配置 root logger，
    # 这里我们确保 Celery 的 logger 也会使用它
    setup_logging()

    # 可选：如果你想确保 Celery 打印的每条日志都经过我们的格式化
    # 我们可以把 Celery 内部的 logger handler 清空，只保留我们的
    # logger.handlers.clear()
    # (如果这一步导致日志不打印了，说明 Celery 的 Logger 需要保留默认 Handler，那就注释掉这行)

    print(f"DEBUG: Celery logging system hijacked. Handlers: {logger.handlers}")