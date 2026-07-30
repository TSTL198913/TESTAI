import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.engine.processor.base import BaseProcessor
from src.core.exceptions import ProcessorError


class TestBaseProcessor:
    class ConcreteProcessor(BaseProcessor):
        async def _run(self, context, step, client):
            return "success"
    
    class FailingProcessor(BaseProcessor):
        async def _run(self, context, step, client):
            raise ValueError("Test error")

    def test_logger_lazy_initialization(self):
        """边界：logger属性懒加载，未初始化时不抛出异常"""
        processor = self.ConcreteProcessor()
        
        assert hasattr(processor, "_logger") is False
        
        logger = processor.logger
        
        assert hasattr(processor, "_logger") is True
        assert logger is not None

    def test_logger_reuses_instance(self):
        """正向：logger属性只初始化一次"""
        processor = self.ConcreteProcessor()
        
        logger1 = processor.logger
        logger2 = processor.logger
        
        assert logger1 is logger2

    @pytest.mark.asyncio
    async def test_process_success(self):
        """正向：process方法成功执行"""
        processor = self.ConcreteProcessor()
        context = MagicMock()
        step = MagicMock()
        client = MagicMock()
        
        result = await processor.process(context, step, client)
        
        assert result == "success"

    @pytest.mark.asyncio
    async def test_process_exception_raises_processor_error(self):
        """异常：process方法捕获异常并抛出ProcessorError"""
        processor = self.FailingProcessor()
        context = MagicMock()
        step = MagicMock()
        client = MagicMock()
        
        with pytest.raises(ProcessorError) as exc_info:
            await processor.process(context, step, client)
        
        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_exception_preserves_original(self):
        """异常：ProcessorError保留原始异常上下文"""
        processor = self.FailingProcessor()
        context = MagicMock()
        step = MagicMock()
        client = MagicMock()
        
        with pytest.raises(ProcessorError) as exc_info:
            await processor.process(context, step, client)
        
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert str(exc_info.value.__cause__) == "Test error"

    @pytest.mark.asyncio
    async def test_process_logs_error(self):
        """异常：process方法记录错误日志"""
        processor = self.FailingProcessor()
        context = MagicMock()
        step = MagicMock()
        client = MagicMock()
        
        with patch.object(processor.logger, "error") as mock_error:
            try:
                await processor.process(context, step, client)
            except ProcessorError:
                pass
            
            mock_error.assert_called_once()
            assert "FailingProcessor failed" in mock_error.call_args[0][0]