import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.storage.repository import ResultRepository


class TestResultRepositoryErrorHandling:
    @pytest.mark.asyncio
    async def test_save_execution_raises_connection_error_when_db_none(self):
        repo = ResultRepository()
        
        with pytest.raises(ConnectionError, match="not initialized"):
            await repo.save_execution("test_step", {"status": "PASSED"})

    @pytest.mark.asyncio
    async def test_save_execution_uses_context_manager(self):
        mock_db = AsyncMock()
        mock_db.execution_results.insert_one = AsyncMock()
        
        async with ResultRepository(db=mock_db) as repo:
            await repo.save_execution("test_step", {"status": "PASSED"})
        
        mock_db.execution_results.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_execution_distinct_error_types(self):
        mock_db = AsyncMock()
        mock_db.execution_results.insert_one = AsyncMock(side_effect=ValueError("Validation error"))
        
        async with ResultRepository(db=mock_db) as repo:
            with pytest.raises(ConnectionError):
                await repo.save_execution("test_step", {"status": "PASSED"})