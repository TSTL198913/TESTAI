"""
HTTPProcessor 单元测试
覆盖:
1. 正常流程 (2xx, JSON/text body 解析)
2. 状态码分支 (500→InfrastructureError, 400→EngineError)
3. 异常分类 (RequestError/网络关键词/未知异常)
4. 重试机制 (500 连续错误触发 retry, 400 不重试)
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from src.engine.processor.http import HTTPProcessor
from src.models.contract import HttpRequest
from src.core.exceptions import EngineError, InfrastructureError


@pytest.fixture
def processor():
    return HTTPProcessor()


@pytest.fixture
def context():
    """模拟 pipeline context (带 results 属性的对象, 匹配 http.py 的 context.results 访问)"""
    class MockContext:
        def __init__(self):
            self.results = {}
    return MockContext()


def _make_step(step_id="s1", url="http://example.com/api/test", method="GET", **kwargs):
    return HttpRequest(step_id=step_id, description="test", url=url, method=method, **kwargs)


def _make_mock_response(status_code=200, content_type="application/json", body=None):
    """构造 mock httpx.Response"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    if body is not None:
        resp.json = MagicMock(return_value=body)
        resp.text = str(body)
    else:
        resp.json = MagicMock(return_value={})
        resp.text = ""
    return resp


@pytest.mark.asyncio
async def test_http_processor_success_json(processor, context):
    """测试: 200 状态码, JSON 响应解析 — 正常流程"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=200, body={"result": "ok", "code": 0})
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_response.aclose = AsyncMock()

    step = _make_step()
    result = await processor.process(context, step, mock_client)

    assert result is step
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["status_code"] == 200
    assert context.results["s1"]["body"] == {"result": "ok", "code": 0}


@pytest.mark.asyncio
async def test_http_processor_success_text_content_type(processor, context):
    """测试: 200 状态码, text/plain 响应 — 非 JSON 解析"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=200, content_type="text/plain", body="Hello World")
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_response.aclose = AsyncMock()

    step = _make_step()
    result = await processor.process(context, step, mock_client)

    assert result is step
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["body"] == "Hello World"


@pytest.mark.asyncio
async def test_http_processor_500_raises_infrastructure_error(processor, context):
    """测试: 500 状态码 → InfrastructureError (触发重试)"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=500)
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_response.aclose = AsyncMock()

    step = _make_step()
    with pytest.raises(InfrastructureError) as exc_info:
        await processor.process(context, step, mock_client)

    assert "Server error 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_processor_400_raises_engine_error(processor, context):
    """测试: 400 状态码 → EngineError (不重试)"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=404)
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_response.aclose = AsyncMock()

    step = _make_step()
    with pytest.raises(EngineError) as exc_info:
        await processor.process(context, step, mock_client)

    assert "Client error 404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_processor_request_error_categorized_as_infrastructure(processor, context):
    """测试: httpx.RequestError → InfrastructureError (网络异常分类)"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    step = _make_step()
    with pytest.raises(InfrastructureError) as exc_info:
        await processor.process(context, step, mock_client)

    assert "Network error" in str(exc_info.value)
    assert "ConnectError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_processor_timeout_keyword_categorized_as_infrastructure(processor, context):
    """测试: 通用异常含 timeout 关键词 → InfrastructureError (异常关键词分类)"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(side_effect=RuntimeError("Request timeout occurred"))

    step = _make_step()
    with pytest.raises(InfrastructureError) as exc_info:
        await processor.process(context, step, mock_client)

    assert "Network error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_processor_unknown_exception_raises_engine_error(processor, context):
    """测试: 通用异常不含关键词 → EngineError (未知异常分类)"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(side_effect=ValueError("Something went wrong"))

    step = _make_step()
    with pytest.raises(EngineError) as exc_info:
        await processor.process(context, step, mock_client)

    assert "Unexpected error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_processor_retry_on_500_then_success(processor, context):
    """测试: 前两次 500 失败,第三次成功 — 验证重试机制"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    resp_500_1 = _make_mock_response(status_code=500)
    resp_500_2 = _make_mock_response(status_code=500)
    resp_ok = _make_mock_response(status_code=200, body={"ok": True})
    
    for r in [resp_500_1, resp_500_2, resp_ok]:
        r.aclose = AsyncMock()
    
    mock_client.request = AsyncMock(side_effect=[resp_500_1, resp_500_2, resp_ok])

    step = _make_step()
    result = await processor.process(context, step, mock_client)

    # 应该被调用了 3 次 (2 次 500 失败 + 1 次成功)
    assert mock_client.request.call_count == 3
    assert result is step
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["status_code"] == 200


@pytest.mark.asyncio
async def test_http_processor_retry_exhausted_on_500(processor, context):
    """测试: 连续 500 超过重试次数 — 最终抛 InfrastructureError
    
    stop_after_attempt(3) 意味着总共最多执行 3 次 (1 初始 + 2 重试)
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    # 返回 3 次 500 (重试上限 3 次)
    responses = [_make_mock_response(status_code=500) for _ in range(3)]
    for r in responses:
        r.aclose = AsyncMock()
    
    mock_client.request = AsyncMock(side_effect=responses)

    step = _make_step()
    with pytest.raises(InfrastructureError):
        await processor.process(context, step, mock_client)
    
    # 应该被调用了 3 次
    assert mock_client.request.call_count == 3


@pytest.mark.asyncio
async def test_http_processor_no_retry_on_400(processor, context):
    """测试: 400 错误不触发重试 — 只调用一次"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=400)
    mock_response.aclose = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    step = _make_step()
    with pytest.raises(EngineError):
        await processor.process(context, step, mock_client)

    # 只调用 1 次, 没有重试
    assert mock_client.request.call_count == 1


@pytest.mark.asyncio
async def test_http_processor_request_params_transform(processor, context):
    """测试: params 中的 list 值提取为单值"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=200, body={"status": "ok"})
    mock_response.aclose = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    step = _make_step(
        params={"foo": ["bar", "baz"], "single": "val"}
    )
    await processor.process(context, step, mock_client)

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["params"] == {"foo": "bar", "single": "val"}


@pytest.mark.asyncio
async def test_http_processor_with_headers(processor, context):
    """测试: headers 正确传递到请求"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=200, body={})
    mock_response.aclose = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    step = _make_step(
        headers={"Authorization": "Bearer token", "X-Custom": "value"}
    )
    await processor.process(context, step, mock_client)

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["headers"] == {"Authorization": "Bearer token", "X-Custom": "value"}


@pytest.mark.asyncio
async def test_http_processor_with_body(processor, context):
    """测试: body 正确传递为 json 参数"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = _make_mock_response(status_code=200, body={"received": True})
    mock_response.aclose = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    step = _make_step(
        method="POST",
        body={"name": "test", "count": 42}
    )
    await processor.process(context, step, mock_client)

    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["json"] == {"name": "test", "count": 42}