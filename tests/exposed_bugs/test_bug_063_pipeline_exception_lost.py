"""BUG-063: Pipeline 异常信息丢失 - 多个步骤失败时只抛出第一个异常，后续异常信息丢失。

源码位置: src/engine/pipeline.py:59-60

根因:
1. 第59-60行只抛出第一个异常 `raise all_exceptions[0]`
2. 虽然上下文已记录所有异常，但当调用方捕获异常时，只能获取第一个异常的信息
3. 多步骤失败场景下，诊断信息不完整

修复方案:
- 当多个步骤失败时，抛出 PipelineError 复合异常
- PipelineError.errors 属性包含所有异常
- 消息包含错误数量统计
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.base import BaseProcessor
from src.core.exceptions import ProcessorError, PipelineError


class MockFailedProcessor(BaseProcessor):
    """模拟失败的处理器"""
    def __init__(self, error_message):
        self._error_message = error_message
    
    async def _run(self, context, step, client):
        raise ValueError(self._error_message.format(step_id=step.step_id))


class TestPipelineExceptionLost:
    """Pipeline异常信息丢失测试"""

    def test_multiple_step_failures_lose_subsequent_errors(self):
        """多个步骤失败时，应抛出包含所有异常的 PipelineError"""
        processor = MockFailedProcessor("Step {step_id} failed")
        
        pipeline = ExecutionPipeline([processor])
        
        context = MagicMock()
        context.results = {}
        
        raw_steps = [
            {
                "step_id": "step-001",
                "description": "Test Step 1",
                "protocol": "http",
                "url": "http://localhost/test",
                "method": "GET",
            },
            {
                "step_id": "step-002",
                "description": "Test Step 2",
                "protocol": "http",
                "url": "http://localhost/test2",
                "method": "GET",
            },
        ]
        
        client = AsyncMock()
        
        with pytest.raises(PipelineError) as exc_info:
            import asyncio
            asyncio.run(pipeline.run(context, raw_steps, client))
        
        pipeline_error = exc_info.value
        assert "2 errors" in str(pipeline_error)
        assert len(pipeline_error.errors) == 2
        assert "step-001" in str(pipeline_error.errors[0])
        assert "step-002" in str(pipeline_error.errors[1])

    def test_all_exceptions_recorded_in_context(self):
        """所有异常都应该记录在上下文中"""
        processor = MockFailedProcessor("Test error for {step_id}")
        
        pipeline = ExecutionPipeline([processor])
        
        context = MagicMock()
        context.results = {}
        
        raw_steps = [
            {
                "step_id": "step-001",
                "description": "Test Step 1",
                "protocol": "http",
                "url": "http://localhost/test",
                "method": "GET",
            },
            {
                "step_id": "step-002",
                "description": "Test Step 2",
                "protocol": "http",
                "url": "http://localhost/test2",
                "method": "GET",
            },
        ]
        
        client = AsyncMock()
        
        try:
            import asyncio
            asyncio.run(pipeline.run(context, raw_steps, client))
        except Exception:
            pass
        
        assert "step-001" in context.results
        assert context.results["step-001"]["status"] == "FAILED"
        assert "step-002" in context.results
        assert context.results["step-002"]["status"] == "FAILED"

    def test_single_step_multiple_processors_all_failures_recorded(self):
        """单步骤多个处理器失败时，所有失败都应记录"""
        processor1 = MockFailedProcessor("Processor 1 error")
        processor2 = MockFailedProcessor("Processor 2 error")
        
        pipeline = ExecutionPipeline([processor1, processor2])
        
        context = MagicMock()
        context.results = {}
        
        raw_steps = [{
            "step_id": "step-001",
            "description": "Test Step",
            "protocol": "http",
            "url": "http://localhost/test",
            "method": "GET",
        }]
        
        client = AsyncMock()
        
        try:
            import asyncio
            asyncio.run(pipeline.run(context, raw_steps, client))
        except Exception:
            pass
        
        step_result = context.results["step-001"]
        assert step_result["status"] == "FAILED"
        assert "Processor 1 error" in step_result["error"]