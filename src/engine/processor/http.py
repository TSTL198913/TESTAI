# src/engine/processor/http.py
import asyncio
import logging
from typing import Dict, Any, Optional

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


class HTTPProcessor(BaseProcessor):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(InfrastructureError),
        before_sleep=lambda retry_state: logger.warning(
            f"正在重试第 {retry_state.attempt_number} 次..."
        ),
        reraise=True,
    )
    async def process(
        self, context, step: HttpRequest, client: httpx.AsyncClient
    ) -> HttpRequest:
        request_kwargs: Dict[str, Any] = {
            "method": step.method,
            "url": str(step.url),
        }
        
        if step.headers:
            request_kwargs["headers"] = dict(step.headers)
        
        if step.params:
            request_kwargs["params"] = {
                k: v[0] if isinstance(v, (list, tuple)) else v 
                for k, v in step.params.items()
            }
        
        if step.body:
            request_kwargs["json"] = step.body

        response = None
        try:
            response = await client.request(**request_kwargs)

            # 3. 核心治理逻辑...
            if response.status_code >= 500:
                raise InfrastructureError(f"Server error {response.status_code}")
            if response.status_code >= 400:
                raise EngineError(f"Client error {response.status_code}")

            # 4. 解析与记录
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                json_method = response.json()
                body = await json_method if asyncio.iscoroutine(json_method) else json_method
            else:
                body = response.text
            context.results[step.step_id] = StepResult(
                status="PASSED", status_code=response.status_code, body=body, error=None
            ).model_dump()

        except httpx.RequestError as e:
            raise InfrastructureError(f"Network error: {type(e).__name__}") from e
        except InfrastructureError:
            raise
        except EngineError:
            raise
        except Exception as e:
            if any(keyword in str(e).lower() for keyword in ["network", "timeout", "connect", "socket", "unreachable"]):
                raise InfrastructureError(f"Network error: {str(e)}") from e
            raise EngineError(f"Unexpected error: {str(e)}") from e
        finally:
            if response is not None:
                try:
                    await response.aclose()
                except Exception:
                    pass

        return step  # 必须返回 step，供下一环处理
