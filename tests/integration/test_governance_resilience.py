import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.governance.resilience import CircuitState
from src.governance.sdk import GovernanceClientSDK


@pytest.fixture
def sdk():
    """提供一个已初始化的 SDK"""
    GovernanceClientSDK.reset_instance()
    return GovernanceClientSDK()


@pytest.mark.asyncio
async def test_circuit_breaker_full_lifecycle(sdk):
    """
    全面测试熔断器生命周期：正常 -> 故障触发 -> 熔断打开 -> 自动恢复
    """
    # 1. 模拟 OpenAI 客户端
    sdk.client.chat.completions.create = AsyncMock()

    # --- 阶段 A: 正常执行 ---
    sdk.client.chat.completions.create.return_value = AsyncMock()
    await sdk.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert sdk.breaker.state == CircuitState.CLOSED

    # --- 阶段 B: 模拟故障触发熔断 ---
    # 连续 3 次失败 (根据我们在 CircuitBreaker 设置的阈值)
    sdk.client.chat.completions.create.side_effect = Exception("API Down")

    for _ in range(3):
        with pytest.raises(Exception, match="API Down"):
            await sdk.chat_completion(messages=[{"role": "user", "content": "hi"}])

    # 验证状态已进入熔断 (OPEN)
    assert sdk.breaker.state == CircuitState.OPEN

    # 【关键修复】：重置 Mock 计数器
    # 这样 call_count 归零，我们就能验证阶段 C 是否真的没有调用 API
    sdk.client.chat.completions.create.reset_mock()

    # --- 阶段 C: 熔断状态下的拒绝保护 ---
    # 再次调用，此时不应调用 API，直接抛出熔断异常
    with pytest.raises(RuntimeError, match="Circuit Breaker is OPEN"):
        await sdk.chat_completion(messages=[{"role": "user", "content": "hi"}])

    # 现在断言 0 次调用，这才是最严谨的“熔断拦截”验证
    assert sdk.client.chat.completions.create.call_count == 0
