# src/storage/repository.py
import logging
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import settings
from src.storage.utils import sanitize_for_mongo

logger = logging.getLogger(__name__)

class ResultRepository:
    def __init__(self, uri: str = None, db=None):
        self.uri = uri
        self.db = db
        self.client = None

    async def __aenter__(self):
        if self.db is None and self.uri:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client.get_database()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 必须存在此方法，即使什么都不做
        if self.client:
            self.client.close()

    async def save_execution(self, step_id: str, results: dict) -> None:
        # 这里必须确保 self.db 已经初始化，否则会抛出 AttributeError
        if self.db is None:
            raise ConnectionError("Repository not initialized. Use 'async with' context manager.")

        try:
            # 1. 数据清洗
            clean_results = sanitize_for_mongo(results)

            # 2. 构造文档
            document = {
                "step_id": step_id,
                "results": clean_results,
                "timestamp": datetime.utcnow()
            }

            # 3. 执行写入
            await self.db.execution_results.insert_one(document)
            logger.info(f"Successfully saved execution result: {step_id}")

        except Exception as e:
            # 区分错误类型
            logger.error(f"Persistence layer failure for {step_id}: {str(e)}")
            raise ConnectionError(f"Database write failed: {e}") from e