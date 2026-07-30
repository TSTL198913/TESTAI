import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.engine.processor.dispatcher import DispatchProcessor


class TestDispatchProcessor:
    @pytest.fixture
    def dispatcher(self):
        return DispatchProcessor()

    @pytest.mark.asyncio
    async def test_dispatch_to_http_processor(self, dispatcher):
        """正向：分发到HTTP处理器"""
        context = MagicMock()
        step = MagicMock()
        step.protocol = "HTTP"
        client = MagicMock()
        
        mock_processor = AsyncMock()
        mock_processor.process.return_value = "http_result"
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            mock_get.return_value = mock_processor
            
            result = await dispatcher.process(context, step, client)
            
            mock_get.assert_called_once_with("http")
            mock_processor.process.assert_called_once_with(context, step, client)
            assert result == "http_result"

    @pytest.mark.asyncio
    async def test_dispatch_to_grpc_processor(self, dispatcher):
        """正向：分发到gRPC处理器"""
        context = MagicMock()
        step = MagicMock()
        step.protocol = "GRPC"
        client = MagicMock()
        
        mock_processor = AsyncMock()
        mock_processor.process.return_value = "grpc_result"
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            mock_get.return_value = mock_processor
            
            result = await dispatcher.process(context, step, client)
            
            mock_get.assert_called_once_with("grpc")
            mock_processor.process.assert_called_once_with(context, step, client)
            assert result == "grpc_result"

    @pytest.mark.asyncio
    async def test_dispatch_protocol_case_insensitive(self, dispatcher):
        """边界：协议名称大小写不敏感"""
        context = MagicMock()
        step = MagicMock()
        step.protocol = "Http"
        client = MagicMock()
        
        mock_processor = AsyncMock()
        mock_processor.process.return_value = "result"
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            mock_get.return_value = mock_processor
            
            await dispatcher.process(context, step, client)
            
            mock_get.assert_called_once_with("http")

    @pytest.mark.asyncio
    async def test_dispatch_unknown_protocol_raises_error(self, dispatcher):
        """负向：未知协议抛出ValueError"""
        context = MagicMock()
        step = MagicMock()
        step.protocol = "UNKNOWN_PROTOCOL"
        client = MagicMock()
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            mock_get.side_effect = ValueError("未找到协议 unknown_protocol 对应的 Processor")
            
            with pytest.raises(ValueError) as exc_info:
                await dispatcher.process(context, step, client)
            
            assert "未找到协议 unknown_protocol 对应的 Processor" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dispatch_preserves_context_and_client(self, dispatcher):
        """正向：分发时保留context和client参数"""
        context = MagicMock()
        context.results = {}
        step = MagicMock()
        step.protocol = "http"
        step.step_id = "test_step"
        client = MagicMock()
        
        mock_processor = AsyncMock()
        mock_processor.process.return_value = step
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            mock_get.return_value = mock_processor
            
            result = await dispatcher.process(context, step, client)
            
            call_args = mock_processor.process.call_args
            assert call_args[0][0] is context
            assert call_args[0][1] is step
            assert call_args[0][2] is client
            assert result is step