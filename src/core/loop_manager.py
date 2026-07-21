import asyncio
import logging
import threading

logger = logging.getLogger("LoopManager")


class AsyncLoopManager:
    _loop: asyncio.AbstractEventLoop = None
    _thread: threading.Thread = None
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
    def run_coroutine(cls, coro):
        if cls._loop is None:
            cls.start()
        return asyncio.run_coroutine_threadsafe(coro, cls._loop)

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
