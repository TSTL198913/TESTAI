import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.engine.processor.governance_processor import GovernanceProcessor


class TestGovernanceProcessorReturnsStep:
    def test_process_method_returns_step(self):
        processor = GovernanceProcessor()
        context = MagicMock()
        context.results = {"test_step": {"status": "PASSED"}}
        step = MagicMock()
        step.step_id = "test_step"

        result = processor.process(context, step, None)

        assert result is not None, "process() should return a value"

    @pytest.mark.asyncio
    async def test_process_with_validation_failure_returns_step(self):
        processor = GovernanceProcessor()
        context = MagicMock()
        context.results = {"test_step": {"status": "FAILED", "error": "test error"}}
        step = MagicMock()
        step.step_id = "test_step"
        step.processor = "test_processor"
        step.model_dump = MagicMock(return_value={})

        with patch.object(processor.engine, "execute_governance_flow", return_value={"status": "DIAGNOSED"}):
            result = await processor.process(context, step, None)

        assert result is not None, "process() should return step even when governance is triggered"