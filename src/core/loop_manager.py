import asyncio
import concurrent.futures
import contextvars
import logging
import threading
from typing import Optional

logger = logging.getLogger("LoopManager")


class AsyncLoopManager:
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _lock = threading.Lock()

    @classmethod
    def start(cls):
        with cls._lock:
            if cls._loop is None:
                cls._loop = asyncio.new_event_loop()
                cls._thread = threading.Thread(
                    target=cls._loop.run_forever, daemon=True
                )
                cls._thread.start()
                logger.info("Background Async Loop started.")

    @classmethod
    def run_coroutine(cls, coro) -> concurrent.futures.Future:
        """将协程调度到后台事件循环执行，返回 concurrent.futures.Future。

        P2-3 修复: 捕获调用线程的 contextvar context 并传播到后台 loop。
        原实现用 asyncio.run_coroutine_threadsafe(coro, cls._loop)，该 API
        不传播 contextvars，导致后台协程中 trace_id 等上下文恒为默认值
        （如 "system"），链路追踪对异步任务完全失效。

        修复方式：在调用线程 contextvars.copy_context() 捕获上下文，
        通过 loop.call_soon_threadsafe + loop.create_task(coro, context=ctx)
        在后台 loop 的指定 ctx 中运行协程（Python 3.11+）。
        返回的 concurrent.futures.Future 与原 API 返回类型兼容。
        """
        if cls._loop is None:
            cls.start()
        # 捕获调用线程的 contextvar 上下文
        ctx = contextvars.copy_context()
        future: concurrent.futures.Future = concurrent.futures.Future()

        def _schedule():
            try:
                # Python 3.11+: create_task 接受 context 参数，在指定 ctx 中运行协程
                task = cls._loop.create_task(coro, context=ctx)
            except TypeError:
                # Python <3.11 回退：contextvars 不传播（记录警告）
                task = asyncio.ensure_future(coro, loop=cls._loop)
                logger.warning(
                    "Python <3.11: contextvars not propagated to background loop"
                )

            def _on_done(t):
                if t.cancelled():
                    future.set_exception(asyncio.CancelledError())
                    return
                exc = t.exception()
                if exc is not None:
                    future.set_exception(exc)
                else:
                    future.set_result(t.result())

            task.add_done_callback(_on_done)

        cls._loop.call_soon_threadsafe(_schedule)
        return future

    @classmethod
    def stop(cls):
        with cls._lock:
            if cls._loop is not None:
                cls._loop.stop()
                if cls._thread is not None:
                    cls._thread.join(timeout=5)
                cls._loop = None
                cls._thread = None
                logger.info("Background Async Loop stopped.")
