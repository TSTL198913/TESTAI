import httpx
import pytest
import respx  # 确保导入

from src.core.container import ResourceContainer
from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.data import DataProcessor
from src.engine.processor.dispatcher import DispatchProcessor
from src.engine.processor.env import EnvironmentProcessor
from src.models.contract import HttpRequest

# ...


@pytest.mark.asyncio
@respx.mock  # 添加装饰器
async def test_http_executor_real_traffic():
    # 拦截请求
    respx.post("https://httpbin.org/anything").mock(
        return_value=httpx.Response(
            200,
            json={
                "args": {"q": "python", "category": "test"},
                "headers": {"X-Engine-Name": "Gemini-Test-Platform"},
                "json": {"user_id": 12345, "action": "login"},
            },
        )
    )
    """
    真实流量测试：验证 HTTPProcessor 的参数映射准确性
    """
    context = ExecutionContext(
        case_id="real_http_test", env={"base_url": "https://httpbin.org"}
    )

    test_params = {"q": "python", "category": "test"}
    test_body = {"user_id": 12345, "action": "login"}
    test_headers = {"X-Engine-Name": "Gemini-Test-Platform"}

    step = HttpRequest(
        step_id="step_real_001",
        description="真实网络请求测试",
        url="https://httpbin.org/anything",
        method="POST",
        headers=test_headers,
        params=test_params,
        body=test_body,
    )

    client = await ResourceContainer.get_client()

    # 【架构重构】：使用 DispatchProcessor 替代 ExecutorAdapter
    pipeline = ExecutionPipeline(
        processors=[
            EnvironmentProcessor({"base_url": "https://httpbin.org"}),
            DataProcessor(),
            DispatchProcessor(),
        ]
    )

    # 执行 (protocol="http" 触发 DispatchProcessor 路由至 HTTPProcessor)
    await pipeline.run(
        context, [{"protocol": "http", "http": step.model_dump()}], client
    )

    result = context.results.get("step_real_001")
    assert result is not None
    assert result["status_code"] == 200

    echoed_data = result["body"]

    # 验证逻辑
    assert echoed_data["args"]["q"] == "python"
    assert echoed_data["headers"]["X-Engine-Name"] == "Gemini-Test-Platform"
    assert echoed_data["json"]["user_id"] == 12345

    print(f"\n[Success] 真实网络映射验证通过，回显数据: {echoed_data}")
