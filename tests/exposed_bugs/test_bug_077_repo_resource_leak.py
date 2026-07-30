import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from src.core.container import ResourceContainer


class TestRepoResourceLeak:
    def test_repo_not_initialized_calls_aenter(self):
        """测试get_repo在repo未初始化时正确调用__aenter__"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()
        container._repo = None
        
        mock_repo_class = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        
        async def test():
            with patch('src.core.container.ResultRepository', mock_repo_class):
                await container.get_repo()
                assert mock_repo_class.call_count == 1
                assert mock_repo.__aenter__.await_count == 1
        
        asyncio.run(test())

    def test_repo_already_exists_no_reinitialization(self):
        """测试repo已存在时不会重新初始化"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()
        
        mock_repo = AsyncMock()
        
        async def test():
            container._repo = mock_repo
            await container.get_repo()
            assert mock_repo.__aenter__.await_count == 0
        
        asyncio.run(test())

    def test_close_calls_aexit(self):
        """测试close方法正确调用__aexit__"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()
        
        mock_repo = AsyncMock()
        mock_client = AsyncMock()
        
        async def test():
            container._repo = mock_repo
            container._client = mock_client
            await container.close()
            assert mock_repo.__aexit__.await_count == 1
            assert mock_client.aclose.await_count == 1
        
        asyncio.run(test())