"""
GrpcProcessor测试 - 仅保留有效测试用例
目标：验证真实业务逻辑，禁止仅验证存在性的弱测试
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.context import ExecutionContext
from src.engine.processor.grpc import GrpcProcessor


class TestGrpcProcessor:
    @pytest.mark.asyncio
    async def test_process_with_default_env(self):
        """正向：处理GRPC请求返回正确结果"""
        processor = GrpcProcessor()
        context = ExecutionContext(case_id="grpc_test_001", env={}, vars={}, results={})

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
        """正向：自定义环境变量生效"""
        processor = GrpcProcessor()
        context = ExecutionContext(
            case_id="grpc_test_002",
            env={"grpc_host": "192.168.1.100", "grpc_port": "50052"},
            vars={},
            results={},
        )

        step = MagicMock()
        step.step_id = "grpc_step_002"
        step.payload = {"user_id": "123"}

        result = await processor.process(context, step, client=None)

        assert result is step
        assert context.results["grpc_step_002"]["status"] == "PASSED"

    @pytest.mark.asyncio
    async def test_process_empty_payload(self):
        """边界：空payload能正常处理"""
        processor = GrpcProcessor()
        context = ExecutionContext(case_id="grpc_test_003", env={}, vars={}, results={})

        step = MagicMock()
        step.step_id = "grpc_step_003"
        step.payload = {}

        result = await processor.process(context, step, client=None)

        assert result is step
        assert context.results["grpc_step_003"]["status"] == "PASSED"
