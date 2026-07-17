# 在测试文件顶部导入 HttpRequest
from src.models.contract import HttpRequest
from src.engine.processor.data import DataProcessor
from src.core.context import ExecutionContext
import pytest


@pytest.mark.asyncio
async def test_pipeline_flow_integration():
    context = ExecutionContext(case_id="unit_test_002")
    context.vars["user_id"] = 999

    # 注入环境参数
    context.env["base_url"] = "https://api.tax.com"

    # 【修复】：补全 HttpRequest 必须的字段，确保符合模型契约
    step = HttpRequest(
        step_id="test_step",
        protocol="http",
        description="Integration test for DataProcessor",  # 补充描述
        url="${base_url}/v1/users",  # 补充 URL
        method="POST",  # 补充方法
        params={
            # 注意：如果模型本身有 url 字段，params 里就不一定需要 request_url 了
            # 我们将具体的参数放入 payload 中，params 依然保留给 DataProcessor 进行渲染
            "payload": {"id": "${user_id}", "type": "admin"}
        }
    )

    data_processor = DataProcessor()

    # 此时 DataProcessor 应该已经渲染了顶层 url
    updated_step = await data_processor.process(context, step=step, client=None)

    # 【修复】：断言指向顶层属性，而不是 params 字典
    assert updated_step.url == "https://api.tax.com/v1/users"

    # 【修复】：将获取的值显式转换为 int
    actual_id = int(updated_step.params["payload"]["id"])
    assert actual_id == 999