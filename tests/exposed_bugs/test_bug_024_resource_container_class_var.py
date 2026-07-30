import pytest
from unittest.mock import patch, AsyncMock
from src.core.container import ResourceContainer


class TestResourceContainerClassVar:
    def test_client_is_instance_variable_not_class_variable(self):
        """边界：_client应是实例变量而非类变量"""
        container = ResourceContainer()
        assert not hasattr(ResourceContainer, "_client") or ResourceContainer._client is None, (
            "_client不应是类变量，应在首次调用get_client时动态创建"
        )

    def test_repo_is_instance_variable_not_class_variable(self):
        """边界：_repo应是实例变量而非类变量"""
        container = ResourceContainer()
        assert not hasattr(ResourceContainer, "_repo") or ResourceContainer._repo is None, (
            "_repo不应是类变量，应在首次调用get_repo时动态创建"
        )

    @pytest.mark.asyncio
    async def test_multiple_instances_share_client(self):
        """正向：单例模式下多个实例共享同一个client"""
        container = ResourceContainer()
        await container.reset_client()
        
        client1 = await container.get_client()
        client2 = await container.get_client()
        
        assert client1 is client2, (
            "单例模式下应共享同一个client"
        )
        
        await container.reset_client()

    @pytest.mark.asyncio
    async def test_reset_client_cleans_up(self):
        """正向：reset_client应清理客户端"""
        container = ResourceContainer()
        client = await container.get_client()
        assert client is not None
        
        await container.reset_client()
        
        client_after_reset = await container.get_client()
        assert client_after_reset is not client, (
            "reset后应创建新的client"
        )