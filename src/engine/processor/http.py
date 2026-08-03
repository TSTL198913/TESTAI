# src/engine/processor/http.py
import asyncio
import ipaddress
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

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


def _validate_url_ssrf(url: str) -> None:
    """P1-2 SSRF 防护：校验目标 URL，拒绝非 http(s) scheme、localhost 与内网/保留地址。

    防护范围：
    - scheme 白名单：仅允许 http/https（拒绝 file://、gopher://、ftp:// 等）
    - 拒绝 localhost 主机名
    - 拒绝字面量为内网/保留/回环/链路本地(含云元数据 169.254.0.0/16)/组播/未指定的 IP

    限制说明：仅做字面量与 hostname 校验，未做 DNS 解析后再校验（防 DNS rebinding）。
    生产环境如需更强防护，应在出网代理层叠加 DNS 解析校验。
    校验失败抛 EngineError（业务异常，不触发 tenacity 重试）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EngineError(
            f"SSRF guard: URL scheme not allowed: {parsed.scheme!r} (only http/https)"
        )
    hostname = parsed.hostname
    if not hostname:
        raise EngineError(f"SSRF guard: URL missing hostname: {url!r}")
    if hostname.lower() == "localhost":
        raise EngineError(f"SSRF guard: localhost target rejected: {url!r}")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # 非字面量 IP（域名），字面量校验通过
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise EngineError(
            f"SSRF guard: internal/reserved IP target rejected: {url!r}"
        )


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
        # P1-2 修复: SSRF 防护 - 发起请求前校验目标 URL
        _validate_url_ssrf(str(step.url))

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
