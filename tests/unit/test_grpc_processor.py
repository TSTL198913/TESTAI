from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.context import ExecutionContext
from src.engine.processor.grpc import GrpcProcessor


class TestGrpcProcessor:
    def test_processor_exists(self):
        assert GrpcProcessor is not None

    def test_processor_has_process_method(self):
        processor = GrpcProcessor()
        # 行为验证：process 必须是可调用的异步方法
        assert callable(getattr(processor, 'process', None)), (
            "GrpcProcessor 必须有 process 方法"
        )

    def test_processor_channel_cache(self):
        # 行为验证：_channels 必须是类变量且为 dict
        channels = getattr(GrpcProcessor, '_channels', None)
        assert channels is not None, "GrpcProcessor 必须有 _channels 类变量"
        assert isinstance(channels, dict), "_channels 必须是 dict 类型"

    def test_processor_get_channel_method(self):
        # 行为验证：_get_channel 必须是类方法且可调用
        get_channel = getattr(GrpcProcessor, '_get_channel', None)
        assert callable(get_channel), (
            "GrpcProcessor 必须有 _get_channel 类方法"
        )

    @pytest.mark.asyncio
    async def test_process_with_default_env(self):
        processor = GrpcProcessor()
        context = ExecutionContext(
            case_id="grpc_test_001",
            env={},
            vars={},
            results={}
        )

        step = MagicMock()
        step.step_id = "grpc_step_001"
        step.payload = {"test": "data"}

        result = await processor.process(context, step, client=None)

        assert result is step
        assert "grpc_step_001" in context.results
        assert context.results["grpc_step_001"]["status"] == "PASSED"
        assert context.results["grpc_step_001"]["body"]["data"] == {"test": "data"}

    @pytest.mark.asyncio
    async def test_process_with_custom_env(self):
        processor = GrpcProcessor()
        context = ExecutionContext(
            case_id="grpc_test_002",
            env={"grpc_host": "192.168.1.100", "grpc_port": "50052"},
            vars={},
            results={}
        )

        step = MagicMock()
        step.step_id = "grpc_step_002"
        step.payload = {"user_id": "123"}

        result = await processor.process(context, step, client=None)

        assert result is step
        assert context.results["grpc_step_002"]["status"] == "PASSED"

    @pytest.mark.asyncio
    async def test_process_empty_payload(self):
        processor = GrpcProcessor()
        context = ExecutionContext(
            case_id="grpc_test_003",
            env={},
            vars={},
            results={}
        )

        step = MagicMock()
        step.step_id = "grpc_step_003"
        step.payload = {}

        result = await processor.process(context, step, client=None)

        assert result is step
        assert context.results["grpc_step_003"]["status"] == "PASSED"

    @pytest.mark.asyncio
    async def test_process_with_client_param(self):
        processor = GrpcProcessor()
        context = ExecutionContext(
            case_id="grpc_test_004",
            env={},
            vars={},
            results={}
        )

        step = MagicMock()
        step.step_id = "grpc_step_004"
        step.payload = {"client_test": "value"}

        mock_client = MagicMock()

        result = await processor.process(context, step, client=mock_client)

        assert result is step
        assert context.results["grpc_step_004"]["status"] == "PASSED"

    def test_processor_inherits_from_base(self):
        from src.engine.processor.base import BaseProcessor
        assert issubclass(GrpcProcessor, BaseProcessor)