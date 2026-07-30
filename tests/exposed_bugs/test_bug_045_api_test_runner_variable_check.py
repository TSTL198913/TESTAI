import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.api_test.test_runner import APITestRunner
from src.api_test.schema import APITestCase, AssertionType


class TestAPITestRunnerVariableCheck:
    @pytest.mark.asyncio
    async def test_run_test_case_handles_exception_properly(self):
        runner = APITestRunner(base_url="http://test.com")
        
        test_case = APITestCase(
            name="Test Exception",
            method="GET",
            url="/test",
            headers={},
            params={},
            body={},
            assertions=[],
        )

        runner.client.send_request = AsyncMock(side_effect=RuntimeError("Test error"))

        result = await runner.run_test_case(test_case)

        assert result.passed is False
        assert result.error_message == "Test error"
        assert result.status_code is None
        assert result.response_time_ms is None

    @pytest.mark.asyncio
    async def test_run_test_case_without_assertions(self):
        runner = APITestRunner(base_url="http://test.com")
        
        test_case = APITestCase(
            name="Test No Assertions",
            method="GET",
            url="/test",
            headers={},
            params={},
            body={},
            assertions=[],
        )

        runner.client.send_request = AsyncMock(return_value=(200, {"data": "test"}, 100.0, {"Content-Type": "application/json"}))

        result = await runner.run_test_case(test_case)

        assert result.passed is True
        assert result.status_code == 200
        assert result.response_time_ms == 100.0