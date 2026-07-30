import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.processor.http import HTTPProcessor
from src.core.exceptions import EngineError, InfrastructureError


class TestHTTPProcessorBoundary:
    @pytest.fixture
    def processor(self):
        return HTTPProcessor()

    @pytest.mark.asyncio
    async def test_process_with_none_step(self, processor):
        """边界：step为None时应抛出错误"""
        context = MagicMock()
        context.results = {}
        step = None
        client = AsyncMock()
        
        with pytest.raises((AttributeError, TypeError)):
            await processor.process(context, step, client)

    @pytest.mark.asyncio
    async def test_process_with_none_method(self, processor):
        """边界：step.method为None时应处理"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = None
        step.url = "http://test.local/api/test"
        step.headers = None
        step.params = None
        step.body = None
        step.step_id = "test_step"
        
        client = AsyncMock()
        
        with pytest.raises(Exception):
            await processor.process(context, step, client)

    @pytest.mark.asyncio
    async def test_process_with_empty_url(self, processor):
        """边界：step.url为空字符串时应处理"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = ""
        step.headers = None
        step.params = None
        step.body = None
        step.step_id = "test_step"
        
        client = AsyncMock()
        
        with pytest.raises(Exception):
            await processor.process(context, step, client)

    @pytest.mark.asyncio
    async def test_process_without_content_type_header(self, processor):
        """边界：响应没有Content-Type头时应处理"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.headers = None
        step.params = None
        step.body = None
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "plain text response"
        client.request.return_value = mock_response
        
        result = await processor.process(context, step, client)
        
        assert result is step
        assert context.results["test_step"]["status"] == "PASSED"
        assert context.results["test_step"]["body"] == "plain text response"

    @pytest.mark.asyncio
    async def test_process_response_json_raises_exception(self, processor):
        """异常：response.json()抛出异常时应处理"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.headers = None
        step.params = None
        step.body = None
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.side_effect = ValueError("Invalid JSON")
        client.request.return_value = mock_response
        
        with pytest.raises(EngineError):
            await processor.process(context, step, client)

    @pytest.mark.asyncio
    async def test_process_500_status_code_raises_infrastructure_error(self, processor):
        """异常：500状态码应抛出InfrastructureError"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "Internal Server Error"
        client.request.return_value = mock_response
        
        with pytest.raises(InfrastructureError) as exc_info:
            await processor.process(context, step, client)
        
        assert "Server error 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_400_status_code_raises_engine_error(self, processor):
        """异常：400状态码应抛出EngineError"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "Bad Request"
        client.request.return_value = mock_response
        
        with pytest.raises(EngineError) as exc_info:
            await processor.process(context, step, client)
        
        assert "Client error 400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_network_error_raises_infrastructure_error(self, processor):
        """异常：网络错误应抛出InfrastructureError"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "test_step"
        
        client = AsyncMock()
        client.request.side_effect = Exception("Network unreachable")
        
        with pytest.raises(InfrastructureError):
            await processor.process(context, step, client)

    @pytest.mark.asyncio
    async def test_process_params_with_list_values(self, processor):
        """边界：params值为列表时应取第一个元素"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.headers = None
        step.params = {"id": ["1", "2", "3"], "name": "test"}
        step.body = None
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}
        client.request.return_value = mock_response
        
        await processor.process(context, step, client)
        
        call_kwargs = client.request.call_args[1]
        assert call_kwargs["params"] == {"id": "1", "name": "test"}

    @pytest.mark.asyncio
    async def test_process_empty_context_results(self, processor):
        """边界：context.results为空字典时应正常工作"""
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}
        client.request.return_value = mock_response
        
        await processor.process(context, step, client)
        
        assert "test_step" in context.results