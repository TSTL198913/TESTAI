# src/engine/processor/http.py
import asyncio
import ipaddress
import logging
import socket
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
    """SSRF 防护：校验 URL 的 scheme 与目标主机安全性。

    业务规则：
    - 仅允许 http/https scheme，拒绝 file/gopher/ftp/dict 等
    - 必须包含 hostname
    - 拒绝回环、链路本地、私有、未指定 IP 及 localhost 主机名

    Args:
        url: 待校验的 URL 字符串

    Raises:
        EngineError: 当 URL 违反 SSRF 防护规则时
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    # 1. Scheme 白名单
    if scheme not in ("http", "https"):
        raise EngineError(
            f"SSRF guard: scheme not allowed '{scheme}'. Only http/https are permitted."
        )

    # 2. Hostname 必须存在
    hostname = parsed.hostname
    if not hostname:
        raise EngineError("SSRF guard: missing hostname in URL.")

    # 3. localhost 文本检查
    if hostname.lower() in ("localhost",):
        raise EngineError(f"SSRF guard: localhost hostname rejected '{hostname}'.")

    # 4. IP 地址检查
    try:
        # 尝试将 hostname 解析为 IP 地址 (支持 IPv4 和 IPv6)
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # hostname 是域名而非 IP — 安全（DNS 解析在请求时进行，
        # 此处不做 DNS 解析以避免 TOCTOU 问题；生产环境应配合
        # httpx 的 transport 层做二次校验）
        return

    # 5. 拒绝非公网 IP
    if ip.is_loopback:
        raise EngineError(f"SSRF guard: loopback IP rejected '{hostname}'.")
    if ip.is_link_local:
        raise EngineError(f"SSRF guard: link-local IP rejected '{hostname}'.")
    if ip.is_private:
        raise EngineError(f"SSRF guard: private IP rejected '{hostname}'.")
    if ip.is_unspecified:
        raise EngineError(f"SSRF guard: unspecified IP rejected '{hostname}'.")


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
        # SSRF 防护：在请求发出前校验 URL 安全性
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
