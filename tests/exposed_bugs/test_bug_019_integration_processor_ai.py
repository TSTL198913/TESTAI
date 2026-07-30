import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.engine.processor.dispatcher import DispatchProcessor
from src.engine.processor.http import HTTPProcessor
from src.ai.defect_analyzer import DefectAnalyzer
from src.ai.test_case_generator import TestCaseGenerator


class TestProcessorAIIntegration:
    @pytest.mark.asyncio
    async def test_dispatcher_uses_http_processor(self):
        """集成：Dispatcher正确调用HTTP处理器"""
        dispatcher = DispatchProcessor()
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.protocol = "HTTP"
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
        mock_response.json.return_value = {"message": "success"}
        client.request.return_value = mock_response
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            http_processor = HTTPProcessor()
            mock_get.return_value = http_processor
            
            result = await dispatcher.process(context, step, client)
            
            mock_get.assert_called_once_with("http")
            client.request.assert_called_once()
            assert result is step
            assert context.results["test_step"]["status"] == "PASSED"

    @pytest.mark.asyncio
    async def test_dispatcher_handles_http_error(self):
        """集成：Dispatcher处理HTTP处理器抛出的错误"""
        dispatcher = DispatchProcessor()
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.protocol = "HTTP"
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "test_step"
        
        client = AsyncMock()
        client.request.side_effect = Exception("Network error")
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            http_processor = HTTPProcessor()
            mock_get.return_value = http_processor
            
            with pytest.raises(Exception):
                await dispatcher.process(context, step, client)

    def test_defect_analyzer_analyzes_test_results_from_processor(self):
        """集成：DefectAnalyzer分析处理器产生的测试结果"""
        analyzer = DefectAnalyzer(llm_api_key=None)
        
        processor_results = {
            "summary": {
                "total_tests": 10,
                "passed": 8,
                "failed": 2,
                "errors": 0,
            },
            "failures": [
                {
                    "test_name": "test_api_call",
                    "error_message": "AssertionError: expected status 200, got 500",
                    "location": "test_processor.py:42",
                    "code_snippet": "response = await client.request(...)",
                },
                {
                    "test_name": "test_data_validation",
                    "error_message": "KeyError: 'expected_field'",
                    "location": "test_processor.py:67",
                    "code_snippet": "data = response.json()",
                },
            ],
            "errors": [],
        }
        
        result = analyzer.analyze_test_results(processor_results)
        
        assert result.success is True
        assert result.total_findings == 2
        assert result.critical_count == 0
        assert result.high_count == 1
        assert result.medium_count == 1
        
        first_finding = result.findings[0]
        assert "AssertionError" in first_finding.description
        assert first_finding.severity.value == "high"

    def test_test_case_generator_generates_cases_from_processor_spec(self):
        """集成：TestCaseGenerator从处理器规范生成测试用例"""
        generator = TestCaseGenerator(llm_api_key=None)
        
        processor_spec = {
            "name": "API测试套件",
            "type": "api",
            "description": "测试HTTP处理器的各种场景",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/health",
                    "params": [],
                },
                {
                    "method": "POST",
                    "path": "/api/users",
                    "params": [
                        {"name": "username", "type": "string", "required": True},
                        {"name": "email", "type": "string", "required": True},
                    ],
                    "body": {
                        "username": "test_user",
                        "email": "test@example.com",
                    },
                },
            ],
        }
        
        result = generator.generate_from_spec(processor_spec)
        
        assert result.success is True
        assert result.total_generated >= 4
        
        health_endpoint_cases = [tc for tc in result.test_cases if "health" in tc.id]
        assert len(health_endpoint_cases) >= 2
        
        users_endpoint_cases = [tc for tc in result.test_cases if "users" in tc.id]
        assert len(users_endpoint_cases) >= 3

    def test_defect_analyzer_analyzes_processor_code(self):
        """集成：DefectAnalyzer分析处理器代码"""
        analyzer = DefectAnalyzer(llm_api_key=None)
        
        processor_code = """
class HTTPProcessor(BaseProcessor):
    async def process(self, context, step, client):
        try:
            response = await client.request(
                method=step.method,
                url=str(step.url),
            )
            if response.status_code >= 500:
                raise InfrastructureError(f"Server error {response.status_code}")
            if response.status_code >= 400:
                raise EngineError(f"Client error {response.status_code}")
            return step
        except:
            pass
"""
        
        result = analyzer.analyze_code(processor_code, "src/engine/processor/http.py")
        
        assert result.success is True
        assert result.total_findings >= 1
        
        silent_exception_finding = next(
            (f for f in result.findings if f.id == "silent_exception"),
            None
        )
        assert silent_exception_finding is not None
        assert silent_exception_finding.severity.value == "medium"

    @pytest.mark.asyncio
    async def test_full_workflow_dispatcher_analyzer(self):
        """集成：Dispatcher调用 + DefectAnalyzer分析的完整工作流"""
        dispatcher = DispatchProcessor()
        analyzer = DefectAnalyzer(llm_api_key=None)
        
        context = MagicMock()
        context.results = {}
        
        step = MagicMock()
        step.protocol = "HTTP"
        step.method = "GET"
        step.url = "http://test.local/api/test"
        step.step_id = "integration_test_step"
        
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}
        client.request.return_value = mock_response
        
        with patch("src.engine.processor.dispatcher.get_processor_instance") as mock_get:
            http_processor = HTTPProcessor()
            mock_get.return_value = http_processor
            
            await dispatcher.process(context, step, client)
            
            assert context.results["integration_test_step"]["status"] == "PASSED"
            
            test_results = {
                "summary": {"total_tests": 1, "passed": 1, "failed": 0, "errors": 0},
                "failures": [],
                "errors": [],
            }
            
            analysis_result = analyzer.analyze_test_results(test_results)
            assert analysis_result.success is True
            assert analysis_result.total_findings == 0