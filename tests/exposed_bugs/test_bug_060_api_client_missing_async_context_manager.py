import pytest
from src.api_test.client import APITestClient


class TestAPIClientMissingAsyncContextManager:
    def test_api_client_supports_async_with(self):
        import asyncio
        
        async def test_async_with():
            async with APITestClient("http://test") as client:
                assert client is not None
        
        asyncio.run(test_async_with())
    
    def test_api_client_has_close_method(self):
        client = APITestClient("http://test")
        assert hasattr(client, "close")
        assert callable(client.close)