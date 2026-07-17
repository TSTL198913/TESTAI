# tests/integration/test_demo_report.py
import pytest
from src.models.contract import Assertion, HttpRequest
from src.engine.processor.assertion import AssertionProcessor
# 【核心调整】确保从 conftest 导入
from tests.conftest import GLOBAL_RESULTS


@pytest.mark.asyncio
async def test_assertion_report_flow():
    step_id = "step_001_login_check"

    # 模拟 HTTP 响应结果
    mock_result = {
        "status": "PENDING",
        "status_code": 200,
        "body": {"code": 0, "data": {"user_id": 123, "role": "admin"}},
        "assertions_history": []
    }

    class MockContext:
        def __init__(self):
            self.results = {step_id: mock_result}

    context = MockContext()

    step = HttpRequest(
        step_id=step_id,
        description="Login authentication test",
        url="https://api.test.com/login",
        method="GET",
        assertions=[
            Assertion(check="status_code", expected=200),
            Assertion(check="jsonpath", path="$.data.role", expected="admin")
        ]
    )

    processor = AssertionProcessor()
    await processor._run(context, step, None)

    # 将结果同步到 conftest 的全局变量
    GLOBAL_RESULTS[step_id] = context.results[step_id]

    assert context.results[step_id]["status"] == "PASSED"