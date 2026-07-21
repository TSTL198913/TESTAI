import os

import pytest

from src.governance.agent import AIGovernanceAgent
from src.governance.config import GovernanceConfig
from src.governance.models import DiagnosticContext
from src.governance.sdk import GovernanceClientSDK


class TestGovernanceConfig:
    def test_default_config(self):
        assert GovernanceConfig.GOVERNANCE_DB_PATH == "./data/governance.sqlite"
        assert GovernanceConfig.LOG_LEVEL == "INFO"
        assert GovernanceConfig.MAX_CONCURRENT_LLM_CALLS == 5

    def test_config_summary(self):
        summary = GovernanceConfig.get_config_summary()
        assert "llm_configured" in summary
        assert "alert_configured" in summary
        assert "db_path" in summary


class TestLLMAvailability:
    def test_sdk_breaker_initialization(self):
        sdk = GovernanceClientSDK()
        assert sdk.breaker is not None

    @pytest.mark.asyncio
    async def test_mock_response(self):
        sdk = GovernanceClientSDK()
        response = await sdk.get_mock_response([{"role": "user", "content": "test"}])
        assert response is not None
        assert isinstance(response.content, str)

    @pytest.mark.asyncio
    async def test_agent_with_mock_response(self):
        agent = AIGovernanceAgent()
        context = DiagnosticContext(
            step_id="step-1",
            component_name="test-component",
            input_data={"test": "input"},
            actual_output={"test": "output"},
            expected_baseline={"test": "expected"},
            exception_trace="TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        )

        from unittest.mock import patch

        with patch.object(agent.sdk, "is_available", return_value=False):
            result = await agent.analyze_with_context(context)
            assert result is not None
            assert result.is_fixable is True
            assert result.confidence_score > 0.0
