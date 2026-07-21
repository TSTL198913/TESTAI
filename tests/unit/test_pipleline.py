from unittest.mock import patch

import pytest

from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.data import DataProcessor
from src.engine.processor.env import EnvironmentProcessor
from src.engine.processor.http import HTTPProcessor
from src.models.contract import HttpRequest


@pytest.mark.asyncio
async def test_pipeline_execution_order():
    context = ExecutionContext(case_id="unit_test_001", env={}, vars={"user": "admin"})

    step = HttpRequest(
        step_id="step_1",
        description="测试流水线编排",
        url="https://api.test.com",
        method="GET",
        params={"target": "${user}"},
    )

    pipeline = ExecutionPipeline(
        processors=[
            EnvironmentProcessor({"base": "https://api.test.com"}),
            DataProcessor(),
        ]
    )

    raw_step = {"protocol": "http", "http": step.model_dump()}

    # 这里假设 pipeline.run 的逻辑是将 step 传递下去并返回最终结果
    with patch.object(HTTPProcessor, "process", return_value=step):
        # 接收 pipeline 的运行结果
        final_steps = await pipeline.run(context, [raw_step], client=None)

        # 直接断言 final_steps 里的对象
        processed_step = final_steps[0]

        # 验证逻辑：这里要注意，DataProcessor 渲染后会更新 step.params
    assert processed_step.params["target"] == "admin"
    assert processed_step.step_id == "step_1"
