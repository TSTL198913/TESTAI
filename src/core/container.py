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

    async def get_repo(self) -> RepositoryProtocol:
        """Get repository instance with MongoDB -> SQLite fallback.
        
        P0-6 Fix: When MONGO_URI is None or MongoDB is unavailable,
        automatically fallback to SQLite for development/testing.
        """
        with self._lock:
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
                self._repo_type = None

    def get_repo_type(self) -> Optional[str]:
        """Get current repository type ('mongodb' or 'sqlite')."""
        return self._repo_type
