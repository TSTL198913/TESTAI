import asyncio
import threading
import pytest
from src.core.container import ResourceContainer


class TestResourceContainer:
    def test_init_multiple_times(self):
        container1 = ResourceContainer()
        container2 = ResourceContainer()
        
        assert container1 is container2
        assert hasattr(container1, '_initialized')
        
        container3 = ResourceContainer()
        assert container3 is container1
        assert container1._initialized is True

    def test_client_loop_mismatch(self):
        """测试客户端在不同事件循环间切换时的处理"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()
        
        async def test_loop_switch():
            client1 = await container.get_client()
            
            new_loop = asyncio.new_event_loop()
            def run_new_loop():
                asyncio.set_event_loop(new_loop)
                new_loop.run_forever()
            
            thread = threading.Thread(target=run_new_loop, daemon=True)
            thread.start()
            
            await asyncio.sleep(0.1)
            
            try:
                future = asyncio.run_coroutine_threadsafe(container.get_client(), new_loop)
                result = future.result(timeout=5)
                assert result is not None
            finally:
                new_loop.stop()
                thread.join(timeout=5)
            
            await container.reset_client()
        
        asyncio.run(test_loop_switch())