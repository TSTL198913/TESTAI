import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.pipeline import ExecutionPipeline


class TestPipelineExceptionSerializable:
    @pytest.mark.asyncio
    async def test_pipeline_results_are_json_serializable(self):
        """边界：pipeline执行结果应可JSON序列化"""
        context = MagicMock()
        context.results = {}
        
        processor = AsyncMock()
        processor.__class__.__name__ = "TestProcessor"
        processor.process.side_effect = ValueError("Test error")
        
        pipeline = ExecutionPipeline([processor])
        
        raw_steps = [{"step_id": "test_step", "protocol": "http", "method": "GET", "url": "http://test.com", "description": "Test step"}]
        client = AsyncMock()
        
        try:
            await pipeline.run(context, raw_steps, client)
        except ValueError:
            pass
        
        assert "test_step" in context.results
        result = context.results["test_step"]
        
        try:
            json.dumps(result)
        except TypeError as e:
            pytest.fail(f"context.results不可JSON序列化: {e}")

    @pytest.mark.asyncio
    async def test_pipeline_stores_error_as_string(self):
        """正向：pipeline应将错误存储为字符串而非原始异常对象"""
        context = MagicMock()
        context.results = {}
        
        processor = AsyncMock()
        processor.__class__.__name__ = "TestProcessor"
        processor.process.side_effect = ValueError("Test error")
        
        pipeline = ExecutionPipeline([processor])
        
        raw_steps = [{"step_id": "test_step", "protocol": "http", "method": "GET", "url": "http://test.com", "description": "Test step"}]
        client = AsyncMock()
        
        try:
            await pipeline.run(context, raw_steps, client)
        except ValueError:
            pass
        
        result = context.results["test_step"]
        assert "error" in result
        assert isinstance(result["error"], str), (
            "error字段应存储为字符串以支持JSON序列化"
        )
        assert result["error"] == "Test error"
        assert "error_type" in result
        assert result["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_pipeline_failure_stores_error_details(self):
        """正向：pipeline失败应存储错误详情"""
        context = MagicMock()
        context.results = {}
        
        processor = AsyncMock()
        processor.__class__.__name__ = "TestProcessor"
        processor.process.side_effect = ValueError("Test error")
        
        pipeline = ExecutionPipeline([processor])
        
        raw_steps = [{"step_id": "test_step", "protocol": "http", "method": "GET", "url": "http://test.com", "description": "Test step"}]
        client = AsyncMock()
        
        try:
            await pipeline.run(context, raw_steps, client)
        except ValueError:
            pass
        
        result = context.results["test_step"]
        assert result["status"] == "FAILED"