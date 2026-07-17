import httpx
import pytest
import respx

from src.core.container import ResourceContainer
from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.assertion import AssertionProcessor
from src.engine.processor.base import ProcessorError
from src.engine.processor.data import DataProcessor
from src.engine.processor.dispatcher import DispatchProcessor
from src.engine.processor.env import EnvironmentProcessor
from src.models.assertion import Assertion
from src.models.contract import HttpRequest


@pytest.mark.asyncio
@respx.mock
async def test_real_network_with_assertions_passed():
    """
    Mock 网络 + 断言全通过测试 (接入 DispatchProcessor)
    """
    respx.get("https://httpbin.org/json").mock(return_value=httpx.Response(
        200,
        json={"slideshow": {"author": "Yours Truly"}}
    ))

    context = ExecutionContext(
        case_id="real_assert_pass",
        env={"base_url": "https://httpbin.org"}
    )

    step = HttpRequest(
        step_id="step_real_001",
        description="JSONPath 校验测试",
        url="https://httpbin.org/json",
        method="GET",
        assertions=[
            Assertion(check="status_code", expected=200),
            Assertion(check="jsonpath", path="$.slideshow.author", expected="Yours Truly")
        ]
    )

    client = await ResourceContainer.get_client()

    # 【架构重构】：使用 DispatchProcessor 替代 ExecutorAdapter
    pipeline = ExecutionPipeline(processors=[
        EnvironmentProcessor({"base_url": "https://httpbin.org"}),
        DataProcessor(),
        DispatchProcessor(),
        AssertionProcessor()
    ])

    raw_step_data = {"protocol": "http", "http": step.model_dump()}

    await pipeline.run(context, [raw_step_data], client)

    result = context.results.get("step_real_001")
    assert result is not None
    assert result["status"] == "PASSED"
    print("\n[Success] Mock 网络测试通过！")


@pytest.mark.asyncio
@respx.mock
async def test_real_network_with_assertions_failed():
    """
    Mock 网络 + 故意让断言失败 (验证熔断)
    """
    respx.get("https://httpbin.org/anything").mock(return_value=httpx.Response(
        200,
        json={"message": "ok"}
    ))

    context = ExecutionContext(
        case_id="real_assert_fail",
        env={"base_url": "https://httpbin.org"}
    )

    step = HttpRequest(
        step_id="step_real_002",
        description="真实网络带断言测试 (预期失败)",
        url="https://httpbin.org/anything",
        method="GET",
        assertions=[
            Assertion(check="status_code", expected=500)
        ]
    )

    client = await ResourceContainer.get_client()

    # 【架构重构】：使用 DispatchProcessor
    pipeline = ExecutionPipeline(processors=[
        EnvironmentProcessor({"base_url": "https://httpbin.org"}),
        DataProcessor(),
        DispatchProcessor(),
        AssertionProcessor()
    ])

    raw_step_data = {"protocol": "http", "http": step.model_dump()}

    with pytest.raises(ProcessorError, match="Assertion Failed"):
        await pipeline.run(context, [raw_step_data], client)

    print("\n[Success] 断言引擎成功拦截了业务逻辑错误！")

