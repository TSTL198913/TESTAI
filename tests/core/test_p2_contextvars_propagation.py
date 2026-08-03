"""P2-3 AsyncLoopManager contextvars 跨线程传播测试。

业务规则（基于代码梳理）：
- AsyncLoopManager.run_coroutine 原用 asyncio.run_coroutine_threadsafe(coro, loop)，
  该 API 不传播 contextvars，后台协程中 trace_id 恒为默认值 "system"，
  链路追踪对异步任务失效。
- 修复后：run_coroutine 用 contextvars.copy_context() 捕获调用线程上下文，
  通过 loop.create_task(coro, context=ctx) 在后台 loop 的指定 ctx 中运行。

覆盖：正向(trace_id传播)/边界(默认值)/异常(协程异常传播)/依赖(不同trace_id隔离)。
"""
import asyncio

import pytest

from src.core.loop_manager import AsyncLoopManager
from src.core.tracer import set_trace_id, reset_trace_id, get_trace_id


class TestContextvarsPropagation:
    """contextvars 跨线程传播：覆盖正向/边界/异常/依赖"""

    def test_trace_id_propagated_to_background_loop(self):
        """正向：主线程 set_trace_id 后，后台协程读到相同 trace_id"""
        token = set_trace_id("trace_xyz")
        try:

            async def get_tid():
                return get_trace_id()

            future = AsyncLoopManager.run_coroutine(get_tid())
            result = future.result(timeout=5)
            # 关键断言：修复前为 "system"，修复后为 "trace_xyz"
            assert result == "trace_xyz", (
                f"后台协程 trace_id 应为 trace_xyz，实际 {result!r}（contextvars 未传播）"
            )
        finally:
            reset_trace_id(token)
            AsyncLoopManager.stop()

    def test_default_trace_id_when_not_set(self):
        """边界：未 set_trace_id 时，后台协程读到默认 'system'"""

        async def get_tid():
            return get_trace_id()

        future = AsyncLoopManager.run_coroutine(get_tid())
        result = future.result(timeout=5)
        assert result == "system"
        AsyncLoopManager.stop()

    def test_exception_propagated_to_future(self):
        """异常：后台协程抛出的异常通过 future 传播"""

        async def boom():
            raise ValueError("bg error")

        future = AsyncLoopManager.run_coroutine(boom())
        with pytest.raises(ValueError, match="bg error"):
            future.result(timeout=5)
        AsyncLoopManager.stop()

    def test_different_trace_ids_isolated(self):
        """依赖：不同 trace_id 的协程互不干扰（各自捕获自己的 ctx）"""
        results = []

        def run_with(tid):
            token = set_trace_id(tid)

            async def get_tid():
                return get_trace_id()

            fut = AsyncLoopManager.run_coroutine(get_tid())
            results.append(fut.result(timeout=5))
            reset_trace_id(token)

        run_with("trace_A")
        run_with("trace_B")
        AsyncLoopManager.stop()

        assert results == ["trace_A", "trace_B"], (
            f"不同 trace_id 应隔离，实际 {results}"
        )

    def test_return_value_propagated(self):
        """正向：后台协程返回值正确传回"""
        import asyncio as _asyncio

        async def compute():
            await _asyncio.sleep(0.01)
            return 42

        future = AsyncLoopManager.run_coroutine(compute())
        assert future.result(timeout=5) == 42
        AsyncLoopManager.stop()
