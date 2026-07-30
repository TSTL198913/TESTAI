"""ResultRepository 测试 - 存储仓库核心功能"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.storage.repository import ResultRepository


class TestResultRepositoryBasics:
    """仓库基础功能测试"""

    def test_init_with_db(self):
        """使用已有的 db 初始化"""
        mock_db = MagicMock()
        repo = ResultRepository(db=mock_db)

        assert repo.db is mock_db
        assert repo.uri is None
        assert repo.client is None

    def test_init_with_uri(self):
        """使用 uri 初始化"""
        repo = ResultRepository(uri="mongodb://localhost:27017/test")

        assert repo.uri == "mongodb://localhost:27017/test"
        assert repo.db is None
        assert repo.client is None


class TestResultRepositoryAsyncContext:
    """异步上下文管理器测试"""

    @pytest.mark.asyncio
    async def test_context_manager_with_uri(self):
        """使用 uri 的上下文管理器"""
        with patch('src.storage.repository.AsyncIOMotorClient') as mock_client:
            mock_client.return_value.get_database.return_value = MagicMock()

            async with ResultRepository(uri="mongodb://localhost:27017/test") as repo:
                assert repo.client is not None
                assert repo.db is not None
                mock_client.assert_called_once_with("mongodb://localhost:27017/test")

            assert repo.client is not None

    @pytest.mark.asyncio
    async def test_context_manager_with_existing_db(self):
        """使用已有 db 的上下文管理器"""
        mock_db = MagicMock()

        async with ResultRepository(db=mock_db) as repo:
            assert repo.db is mock_db
            assert repo.client is None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """退出上下文时关闭客户端"""
        mock_client = MagicMock()
        mock_client.get_database.return_value = MagicMock()

        with patch('src.storage.repository.AsyncIOMotorClient', return_value=mock_client):
            async with ResultRepository(uri="mongodb://localhost:27017/test"):
                pass

            mock_client.close.assert_called_once()


class TestResultRepositorySave:
    """保存执行结果测试"""

    @pytest.mark.asyncio
    async def test_save_execution_success(self):
        """成功保存执行结果"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)
        repo.db = mock_db

        results = {"test_key": "test_value"}
        await repo.save_execution("step_001", results)

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert inserted_doc["step_id"] == "step_001"
        assert inserted_doc["results"] == {"test_key": "test_value"}
        assert "timestamp" in inserted_doc

    @pytest.mark.asyncio
    async def test_save_execution_not_initialized(self):
        """未初始化时保存抛出异常"""
        repo = ResultRepository()
        repo.db = None

        with pytest.raises(ConnectionError, match="Repository not initialized"):
            await repo.save_execution("step_001", {})

    @pytest.mark.asyncio
    async def test_save_execution_database_failure(self):
        """数据库写入失败"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Connection refused")
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)

        with pytest.raises(ConnectionError, match="Database write failed"):
            await repo.save_execution("step_001", {})

    @pytest.mark.asyncio
    async def test_save_execution_with_special_chars(self):
        """保存包含特殊字符的结果"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)

        results = {
            "dot.key": "value",
            "dollar$key": "value",
            "normal_key": "value with spaces",
        }
        await repo.save_execution("step_001", results)

        mock_collection.insert_one.assert_called_once()


class TestResultRepositoryEdgeCases:
    """边界场景测试"""

    @pytest.mark.asyncio
    async def test_save_empty_results(self):
        """保存空结果"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)

        await repo.save_execution("step_001", {})

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert inserted_doc["results"] == {}

    @pytest.mark.asyncio
    async def test_save_nested_results(self):
        """保存嵌套结果"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)

        results = {
            "level1": {
                "level2": {
                    "key": "value",
                    "list": [1, 2, 3],
                }
            }
        }
        await repo.save_execution("step_001", results)

        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_large_results(self):
        """保存大量结果"""
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection

        repo = ResultRepository(db=mock_db)

        large_results = {f"key_{i}": f"value_{i}" for i in range(100)}
        await repo.save_execution("step_001", large_results)

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert len(inserted_doc["results"]) == 100