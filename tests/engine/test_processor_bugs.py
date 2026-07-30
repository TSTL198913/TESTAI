import asyncio
import threading
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.exceptions import EngineError, InfrastructureError, ProcessorError
from src.engine.processor.base import BaseProcessor
from src.engine.processor.grpc import GrpcProcessor
from src.engine.processor.data import DataProcessor
from src.engine.processor.assertion import AssertionProcessor
from src.models.contract import HttpRequest, GrpcRequest, Assertion
from src.models.result import StepResult
from src.core.context import ExecutionContext


class TestBaseProcessorErrorMasking:
    """BUG-080: BaseProcessor捕获所有异常并包装为ProcessorError，掩盖真实错误类型"""
    
    def test_base_processor_masks_original_exception_type(self):
        """验证BaseProcessor将InfrastructureError错误地包装为ProcessorError"""
        class TestProcessor(BaseProcessor):
            async def _run(self, context, step, client):
                raise InfrastructureError("Network timeout")
        
        processor = TestProcessor()
        context = MagicMock()
        
        with pytest.raises(ProcessorError) as exc_info:
            asyncio.run(processor.process(context, MagicMock(), MagicMock()))
        
        assert "Processor TestProcessor failed" in str(exc_info.value)
        assert "Network timeout" in str(exc_info.value)
        assert isinstance(exc_info.value, ProcessorError)
        assert isinstance(exc_info.value.__cause__, InfrastructureError)


class TestGrpcProcessorChannelsConcurrency:
    """BUG-081: GrpcProcessor._channels类变量无锁保护"""
    
    def test_concurrent_channel_access_race_condition(self):
        """验证并发访问_channels可能导致数据竞争"""
        GrpcProcessor._channels = {}
        
        def create_channel(i):
            processor = GrpcProcessor()
            processor._channels[(f"host{i}", 50051)] = f"channel_{i}"
        
        threads = [threading.Thread(target=create_channel, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(GrpcProcessor._channels) == 10


class TestGrpcProcessorNotImplemented:
    """BUG-082: GrpcProcessor._get_channel和核心逻辑未实现 (已修复: P0-5)"""
    
    def test_get_channel_raises_not_implemented_error(self):
        """验证_get_channel方法在gRPC未实现时抛出NotImplementedError"""
        processor = GrpcProcessor()
        with pytest.raises(NotImplementedError) as exc_info:
            processor._get_channel("localhost", 50051)
        assert "gRPC channel not implemented" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_process_raises_engine_error_when_grpc_unavailable(self):
        """验证process方法在gRPC不可用时抛出EngineError，而非假成功"""
        processor = GrpcProcessor()
        context = ExecutionContext(case_id="test_case")
        step = GrpcRequest(
            step_id="test_grpc",
            description="test grpc step",
            payload={"test": "data"},
            service="test",
            method="test_method",
            proto_file_path="test.proto"
        )
        
        with pytest.raises(EngineError) as exc_info:
            await processor.process(context, step, None)
        
        assert "gRPC step 'test_grpc' failed" in str(exc_info.value)


class TestDataProcessorUnusedMethod:
    """BUG-083: DataProcessor._render_and_update方法定义但未使用"""
    
    def test_render_and_update_not_called(self):
        """验证_render_and_update方法在处理过程中从未被调用"""
        processor = DataProcessor()
        context = ExecutionContext(case_id="test_case", env={"base_url": "http://localhost"})
        step = HttpRequest(
            step_id="test_http",
            description="test http step",
            method="GET",
            url="http://localhost/api",
            params={"id": "{{test_id}}"},
            protocol="http"
        )
        
        original_render_and_update = processor._render_and_update
        render_called = [False]
        
        def track_call(*args, **kwargs):
            render_called[0] = True
            return original_render_and_update(*args, **kwargs)
        
        processor._render_and_update = track_call
        
        result = asyncio.run(processor.process(context, step, None))
        
        assert render_called[0] is False


class TestAssertionProcessorJsonPathMultiValue:
    """BUG-084: AssertionProcessor处理jsonpath多值结果时只取第一个"""
    
    def test_jsonpath_multiple_matches_only_takes_first(self):
        """验证jsonpath返回多个匹配时只取第一个可能导致错误断言"""
        processor = AssertionProcessor()
        context = ExecutionContext(case_id="test_case")
        
        context.results["test_step"] = StepResult(
            status="PASSED",
            status_code=200,
            body={"items": [{"id": 1}, {"id": 2}, {"id": 3}]},
            error=None
        ).model_dump()
        
        step = HttpRequest(
            step_id="test_step",
            description="test assertion step",
            method="GET",
            url="http://localhost/api",
            protocol="http",
            assertions=[
                Assertion(check="jsonpath", path="$.items[*].id", expected=3)
            ]
        )
        
        with pytest.raises(EngineError):
            asyncio.run(processor.process(context, step, None))


class TestAssertionProcessorTypeError:
    """BUG-085: AssertionProcessor在比较不同类型时可能失败"""
    
    def test_jsonpath_result_type_mismatch(self):
        """验证jsonpath返回整数但expected是字符串时比较失败"""
        processor = AssertionProcessor()
        context = ExecutionContext(case_id="test_case")
        
        context.results["test_step"] = StepResult(
            status="PASSED",
            status_code=200,
            body={"count": 42},
            error=None
        ).model_dump()
        
        step = HttpRequest(
            step_id="test_step",
            description="test type mismatch step",
            method="GET",
            url="http://localhost/api",
            protocol="http",
            assertions=[
                Assertion(check="jsonpath", path="$.count", expected="42")
            ]
        )
        
        with pytest.raises(EngineError):
            asyncio.run(processor.process(context, step, None))