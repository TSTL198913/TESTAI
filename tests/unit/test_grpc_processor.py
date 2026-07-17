from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.context import ExecutionContext
from src.engine.processor.grpc import GrpcProcessor


class TestGrpcProcessor:
    def test_processor_exists(self):
        assert GrpcProcessor is not None

    def test_processor_has_process_method(self):
        processor = GrpcProcessor()
        assert hasattr(processor, 'process')
        assert callable(processor.process)

    def test_processor_channel_cache(self):
        assert hasattr(GrpcProcessor, '_channels')
        assert isinstance(GrpcProcessor._channels, dict)

    def test_processor_get_channel_method(self):
        assert hasattr(GrpcProcessor, '_get_channel')
        assert callable(GrpcProcessor._get_channel)

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