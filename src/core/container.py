import asyncio
import logging
import threading
from typing import Optional, Any, Protocol

import httpx

from src.core.config import settings
from src.storage.repository import ResultRepository
from src.storage.sqlite_repository import SQLiteResultRepository

logger = logging.getLogger(__name__)


class RepositoryProtocol(Protocol):
    """Protocol for repository implementations (MongoDB or SQLite)."""
    async def __aenter__(self) -> "RepositoryProtocol": ...
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...
    async def save_execution(self, step_id: str, results: dict) -> None: ...


class ResourceContainer:
    _instance = None
    # 仅用于 __new__ 单例创建（同步临界区，不跨越 await）
    _lock = threading.RLock()
    _client: Optional[httpx.AsyncClient] = None
    _repo: Optional[RepositoryProtocol] = None
    _repo_type: Optional[str] = None  # "mongodb" or "sqlite"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._client = None
                cls._instance._repo = None
                cls._instance._repo_type = None
                cls._instance._async_lock = None  # 惰性创建 asyncio.Lock
                cls._instance._lock_loop = None  # P0 修复: 跟踪 Lock 绑定的事件循环
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._async_lock: Optional[asyncio.Lock] = None
        self._lock_loop = None  # 跟踪 _async_lock 绑定的事件循环

    def _get_async_lock(self) -> asyncio.Lock:
        """P1-3 修复 + P0 跨事件循环防御: 惰性创建 asyncio.Lock，并检测事件循环变化。

        原实现在 get_client/get_repo/close 等异步方法中用 `with self._lock`
        (threading.RLock) 跨越 await。问题：
        1) RLock 按线程ID重入，单线程 asyncio 中所有协程同线程 → 可重入获取，
           协程间互斥完全失效，_client/_repo 可能被并发重复创建；
        2) 持同步锁跨越 await 会阻塞事件循环。

        asyncio.Lock 在 await 时让出事件循环，且按协程互斥（非按线程），
        正确保护异步临界区。惰性创建避免无事件循环时实例化。

        P0 修复 (跨事件循环防御):
        asyncio.Lock 在首次 await acquire() 时绑定到当前事件循环。
        单例 ResourceContainer 共享 _async_lock，若事件循环关闭并重启
        (如测试中多次 asyncio.run()，或部署场景中事件循环重建)，
        旧 Lock 仍绑定到已关闭循环，导致:
        - RuntimeError: ... is bound to a different event loop
        - 死锁: 持锁方循环关闭后永不释放，等待方永久阻塞

        修复: 跟踪 _lock_loop，检测到当前运行循环与绑定循环不一致时重建 Lock。
        注意: 这只能防御"循环切换后首次获取"的场景，无法挽救已陷入
        waiters 队列等待旧循环 future 的协程。因此调用方必须保证不在
        持锁期间关闭事件循环(生产环境 FastAPI/Celery 单事件循环天然满足)。

        单线程 asyncio 中此处无 await 间隙，_async_lock 创建/重建原子安全。
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无运行中的事件循环(不应发生在异步方法中，防御性处理)
            current_loop = None

        # 检测事件循环变化: 若 Lock 未创建或绑定循环与当前不一致，重建
        # - _async_lock is None: 首次创建
        # - _lock_loop is not current_loop: 事件循环已切换，旧 Lock 不可用
        if (
            self._async_lock is None
            or self._lock_loop is not current_loop
        ):
            self._async_lock = asyncio.Lock()
            self._lock_loop = current_loop
        return self._async_lock

    async def get_client(self) -> httpx.AsyncClient:
        async with self._get_async_lock():
            if self._client is not None:
                if self._client.is_closed:
                    self._client = None
                else:
                    try:
                        current_loop = asyncio.get_running_loop()
                        if (
                            hasattr(self._client, "_loop")
                            and self._client._loop != current_loop
                        ):
                            await self._client.aclose()
                            self._client = None
                    except RuntimeError:
                        self._client = None

            if self._client is None:
                self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
            return self._client

    async def reset_client(self):
        """测试专用：强制清理客户端"""
        async with self._get_async_lock():
            if self._client:
                if not self._client.is_closed:
                    await self._client.aclose()
                self._client = None

    async def get_repo(self) -> RepositoryProtocol:
        """Get repository instance with MongoDB -> SQLite fallback.

        P0-6 Fix: When MONGO_URI is None or MongoDB is unavailable,
        automatically fallback to SQLite for development/testing.
        """
        async with self._get_async_lock():
            if self._repo is None:
                if settings.MONGO_URI:
                    try:
                        self._repo = ResultRepository(uri=settings.MONGO_URI)
                        await self._repo.__aenter__()
                        self._repo_type = "mongodb"
                        logger.info("Using MongoDB repository")
                    except Exception as e:
                        logger.warning(f"MongoDB connection failed, falling back to SQLite: {e}")
                        self._repo = SQLiteResultRepository()
                        self._repo_type = "sqlite"
                else:
                    # No MONGO_URI configured, use SQLite directly
                    logger.info("MONGO_URI not configured, using SQLite repository")
                    self._repo = SQLiteResultRepository()
                    self._repo_type = "sqlite"
            return self._repo

    async def close(self):
        """关闭所有资源"""
        async with self._get_async_lock():
            if self._client and not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception as e:
                    logger.warning(f"Failed to close HTTP client: {e}")
                self._client = None
            if self._repo:
                try:
                    await self._repo.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Failed to close repository: {e}")
                self._repo = None
                self._repo_type = None

    def get_repo_type(self) -> Optional[str]:
        """Get current repository type ('mongodb' or 'sqlite')."""
        return self._repo_type
