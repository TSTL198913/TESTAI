# tests/integration/test_governance_lifecycle.py
import httpx
import pytest
import respx

from src.core.container import ResourceContainer
from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.assertion import AssertionProcessor
from src.engine.processor.dispatcher import DispatchProcessor
from src.engine.processor.governance_processor import GovernanceProcessor
from src.models.assertion import Assertion
from src.models.contract import HttpRequest
# --- 导入单例 ---
from src.report.storage import registry


@pytest.mark.asyncio
@respx.mock
async def test_governance_lifecycle_triggered():
    # 1. 模拟一个肯定会失败的请求
    # respx.get("https://httpbin.org/status/500").mock(return_value=httpx.Response(500))

    # 1. 模拟业务接口失败 (原有的 500 模拟)
    respx.get("https://httpbin.org/status/500").mock(return_value=httpx.Response(500))

    # 修改 test_governance_lifecycle.py 中的 mock 数据
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{
                "message": {
                    "content": '{"is_fixable": true, "reasoning": "...", "confidence_score": 0.95, "suggested_fix": {"action": "查看 Kubernetes Pod 日志", "priority": "high"}}'
                }
            }]
        })
    )
    context = ExecutionContext(case_id="gov_test")
    client = await ResourceContainer.get_client()

    # 2. 构建 Pipeline
    pipeline = ExecutionPipeline(processors=[
        DispatchProcessor(),
        AssertionProcessor(),
        GovernanceProcessor()
    ])

    # 3. 定义步骤
    step = HttpRequest(
        step_id="gov_step_01",
        description="触发治理的测试",
        url="https://httpbin.org/status/500",
        method="GET",
        assertions=[Assertion(check="status_code", expected=200)]
    )
    step_data = {"protocol": "http", "http": step.model_dump()}

    # 4. 执行（预期断言失败会抛出异常，但治理处理器仍会执行）
    with pytest.raises(Exception):
        await pipeline.run(context, [step_data], client)

    # 5. 验证与注册 (关键步骤)
    result = context.results.get("gov_step_01")
    assert result is not None
    assert "governance_insight" in result, "治理引擎未生成治理报告"

    insight = result["governance_insight"]
    print(f"\n[Success] 治理报告已生成: {insight.get('reasoning')}")
    assert insight.get("reasoning") is not None

    # --- ！！！一定要调用这一行 ！！！ ---
    registry.update(context.case_id, result)
    print(f"[DEBUG] 数据已回传至 Registry。")
