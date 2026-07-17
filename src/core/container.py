import asyncio

import httpx

from src.core.config import settings
from src.storage.repository import ResultRepository


class ResourceContainer:
    _client: httpx.AsyncClient = None
    _repo: ResultRepository = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        # 如果 client 存在但循环已关闭，强制关闭旧 client 并重置
        if cls._client is not None:
            if cls._client.is_closed:
                cls._client = None
            else:
                try:
                    current_loop = asyncio.get_running_loop()
                    if hasattr(cls._client, '_loop') and cls._client._loop != current_loop:
                        await cls._client.aclose()
                        cls._client = None
                except RuntimeError:
                    cls._client = None

        if cls._client is None:
            # 明确使用 timeout 关键字参数，避免 TypeError
            cls._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return cls._client

    @classmethod
    async def reset_client(cls):
        """测试专用：强制清理客户端"""
        if cls._client:
            if not cls._client.is_closed:
                await cls._client.aclose()
            cls._client = None

    @classmethod
    async def get_repo(cls) -> ResultRepository:
        if cls._repo is None:
            cls._repo = ResultRepository(uri=settings.MONGO_URI)
            await cls._repo.__aenter__()
        return cls._repo


