"""P1-3 ResourceContainer 异步锁测试。

业务规则（基于代码梳理）：
- 原实现 get_client/get_repo/reset_client/close 用 `with self._lock`
  (threading.RLock) 跨越 await。threading.RLock 按线程ID重入，
  单线程 asyncio 中所有协程同线程 → 可重入获取，协程间互斥失效，
  _client/_repo 可能被并发重复创建；持同步锁跨越 await 还会阻塞事件循环。
- 修复后：异步方法改用 asyncio.Lock（_get_async_lock 惰性创建），
  按协程互斥，await 时让出事件循环。

覆盖：正向(锁类型/单例)/并发(不超时+同一client)/边界(reset)/依赖(close清理)。
"""
import asyncio
import threading

import pytest

from src.core.container import ResourceContainer


@pytest.fixture
def container():
    c = ResourceContainer()
    return c


class TestContainerAsyncLock:
    """异步锁：覆盖正向/负向/边界/异常/依赖"""

    def test_get_async_lock_returns_asyncio_lock(self, container):
        """正向：_get_async_lock 返回 asyncio.Lock 而非 threading 锁"""
        lock = container._get_async_lock()
        assert isinstance(lock, asyncio.Lock), (
            "异步临界区必须使用 asyncio.Lock，而非 threading.RLock"
        )
        # 验证是异步锁：具备 async __aenter__（threading 锁为同步上下文管理器）
        # callable(getattr(...)) 比 hasattr 更强: 既验证属性存在, 又验证可调用
        assert callable(getattr(type(lock), "__aenter__", None)), (
            "异步锁必须实现 __aenter__ (threading.Lock 无此方法)"
        )

    @pytest.mark.asyncio
    async def test_get_client_returns_client(self, container):
        """正向：get_client 返回 httpx.AsyncClient"""
        await container.reset_client()
        try:
            client = await container.get_client()
            assert client is not None
            assert not client.is_closed
        finally:
            await container.close()

    @pytest.mark.asyncio
    async def test_concurrent_get_client_no_deadlock_single_instance(self, container):
        """并发：10 个协程并发 get_client 不超时，且返回同一 client 实例。

        原 threading.RLock 在单线程 asyncio 中可重入 → 互斥失效，并发可能
        多次创建 client。asyncio.Lock 正确互斥，确保只创建一次。
        """
        await container.reset_client()
        try:
            clients = await asyncio.wait_for(
                asyncio.gather(*[container.get_client() for _ in range(10)]),
                timeout=5.0,
            )
            # 关键断言：并发下只创建一个 client
            assert len({id(c) for c in clients}) == 1, (
                "并发 get_client 应返回同一 client 实例（asyncio.Lock 互斥）"
            )
        finally:
            await container.close()

    @pytest.mark.asyncio
    async def test_reset_client_recreates(self, container):
        """边界：reset_client 后 get_client 返回新 client"""
        await container.reset_client()
        try:
            c1 = await container.get_client()
            await container.reset_client()
            c2 = await container.get_client()
            assert c1 is not c2, "reset 后应创建新的 client"
        finally:
            await container.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, container):
        """依赖：close 后 _client 被清理"""
        await container.reset_client()
        c = await container.get_client()
        assert container._client is c
        await container.close()
        assert container._client is None, "close 后 _client 必须为 None"

    @pytest.mark.asyncio
    async def test_concurrent_get_repo_no_deadlock(self, container):
        """并发：并发 get_repo 不超时（验证异步锁不阻塞事件循环）"""
        try:
            repos = await asyncio.wait_for(
                asyncio.gather(*[container.get_repo() for _ in range(5)]),
                timeout=5.0,
            )
            # 并发下应返回同一 repo 实例
            assert len({id(r) for r in repos}) == 1
        finally:
            await container.close()
