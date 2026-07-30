import pytest
import threading
from src.core.loop_manager import AsyncLoopManager


class TestLoopManagerThreadSafe:
    def test_run_coroutine_is_thread_safe(self):
        AsyncLoopManager._loop = None
        AsyncLoopManager._thread = None

        results = []

        async def dummy_coro(i):
            return f"result_{i}"

        def run_coro_thread(i):
            try:
                future = AsyncLoopManager.run_coroutine(dummy_coro(i))
                results.append(future.result(timeout=5))
            except Exception as e:
                results.append(f"error_{i}: {e}")

        threads = [threading.Thread(target=run_coro_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r.startswith("result_") for r in results), "All threads should get successful results"
        assert len(results) == 10, "All 10 threads should complete"

        AsyncLoopManager.stop()