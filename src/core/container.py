import asyncio
import logging
import threading
from typing import Optional

import httpx

from src.core.config import settings
from src.storage.repository import ResultRepository

logger = logging.getLogger(__name__)


class ResourceContainer:
    _instance = None
    _lock = threading.RLock()
    _client: Optional[httpx.AsyncClient] = None
    _repo: Optional[ResultRepository] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._client = None
                cls._instance._repo = None
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

    async def get_client(self) -> httpx.AsyncClient:
        with self._lock:
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
        with self._lock:
            if self._client:
                if not self._client.is_closed:
                    await self._client.aclose()
                self._client = None

    async def get_repo(self) -> ResultRepository:
        with self._lock:
            if self._repo is None:
                self._repo = ResultRepository(uri=settings.MONGO_URI)
                await self._repo.__aenter__()
            return self._repo

    async def close(self):
        """关闭所有资源"""
        with self._lock:
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
