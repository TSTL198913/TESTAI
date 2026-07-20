# src/engine/processor/http.py
import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.exceptions import EngineError, InfrastructureError
from src.engine.processor.base import BaseProcessor
from src.models.contract import HttpRequest
from src.models.result import StepResult

logger = logging.getLogger("ai_test_platform")


class HTTPProcessor(BaseProcessor):  # 修改类名
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(InfrastructureError),
        before_sleep=lambda retry_state: logger.warning(
            f"正在重试第 {retry_state.attempt_number} 次..."
        ),
    )
    # 增加 client 参数，并添加返回类型
    async def process(
        self, context, step: HttpRequest, client: httpx.AsyncClient
    ) -> HttpRequest:
        # 1. 准备参数映射 (保持原有逻辑)
        request_kwargs = {
            "method": step.method,
            "url": str(step.url),
            "headers": step.headers,
            "params": step.params,
        }
        if step.body:
            request_kwargs["json"] = step.body

        try:
            # 2. 使用传入的 client 发起请求
            response = await client.request(**request_kwargs)

            # 3. 核心治理逻辑...
            if response.status_code >= 500:
                raise InfrastructureError(f"Server error {response.status_code}")
            if response.status_code >= 400:
                raise EngineError(f"Client error {response.status_code}")

            # 4. 解析与记录
            body = (
                response.json()
                if "application/json" in response.headers.get("Content-Type", "")
                else response.text
            )
            context.results[step.step_id] = StepResult(
                status="PASSED", status_code=response.status_code, body=body, error=None
            ).model_dump()

        except httpx.RequestError as e:
            raise InfrastructureError(f"Network error: {type(e).__name__}") from e
        except Exception as e:
            raise EngineError(f"Unexpected error: {str(e)}") from e

        return step  # 必须返回 step，供下一环处理
