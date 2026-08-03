"""P1-2 HTTPProcessor SSRF 防护测试。

业务规则（基于代码梳理）：
- http.py 原实现直接用 str(step.url) 发起请求，无 scheme 白名单、
  无内网过滤，可访问云元数据 169.254.169.254、内网 Redis、file:// 等。
- 修复后：process() 入口先调用 _validate_url_ssrf()，拒绝
  非法 scheme / localhost / 内网保留 IP，抛 EngineError（不重试）。

覆盖：正向(公网)/负向(各类内网与非法scheme)/边界(IPv6/公网IP)。
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from src.engine.processor.http import HTTPProcessor, _validate_url_ssrf
from src.core.exceptions import EngineError


@pytest.fixture
def processor():
    return HTTPProcessor()


@pytest.fixture
def context():
    class MockContext:
        def __init__(self):
            self.results = {}
    return MockContext()


def _make_step(url, step_id="s1", method="GET"):
    from src.models.contract import HttpRequest
    return HttpRequest(step_id=step_id, description="test", url=url, method=method)


def _make_mock_response(status_code=200, body=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.json = MagicMock(return_value=body if body is not None else {})
    resp.text = str(body) if body is not None else ""
    resp.aclose = AsyncMock()
    return resp


class TestSsrfGuardUnit:
    """_validate_url_ssrf 纯函数测试"""

    @pytest.mark.parametrize("url", [
        "https://example.com/api",
        "http://8.8.8.8/health",
        "http://93.184.216.34/index.html",
    ])
    def test_public_urls_pass(self, url):
        """正向：公网域名/公网IP 不抛异常"""
        _validate_url_ssrf(url)  # 不抛即通过

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",  # 云元数据
        "http://localhost:8000/api",       # localhost
        "http://127.0.0.1:6379/",          # 回环
        "http://10.0.0.5/admin",           # 私有 10/8
        "http://192.168.1.1/",             # 私有 192.168/16
        "http://172.16.0.1/",              # 私有 172.16/12
        "http://[::1]:8080/",              # IPv6 回环
        "http://0.0.0.0/",                 # 未指定
    ])
    def test_internal_urls_rejected(self, url):
        """负向：内网/回环/链路本地/未指定 IP 拒绝"""
        with pytest.raises(EngineError, match="SSRF guard"):
            _validate_url_ssrf(url)

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "gopher://attacker.com/x",
        "ftp://internal/repo",
        "dict://localhost:6379/INFO",
    ])
    def test_non_http_schemes_rejected(self, url):
        """负向：非 http(s) scheme 拒绝"""
        with pytest.raises(EngineError, match="scheme not allowed"):
            _validate_url_ssrf(url)

    def test_missing_hostname_rejected(self):
        """边界：无 hostname 拒绝"""
        with pytest.raises(EngineError, match="missing hostname"):
            _validate_url_ssrf("http:///path")


class TestSsrfGuardInProcess:
    """SSRF 校验在 process() 集成测试"""

    @pytest.mark.asyncio
    async def test_ssrf_blocks_request_before_sent(self, processor, context):
        """负向：云元数据 URL 在请求发出前被拒绝，client.request 不应被调用"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        step = _make_step("http://169.254.169.254/latest/meta-data/")

        with pytest.raises(EngineError, match="SSRF guard"):
            await processor.process(context, step, mock_client)

        # 关键断言：请求从未发出
        mock_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_public_url_proceeds_to_request(self, processor, context):
        """正向：公网 URL 校验通过，正常发起请求并记录结果"""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=_make_mock_response(body={"ok": True}))
        step = _make_step("https://example.com/api")

        await processor.process(context, step, mock_client)

        mock_client.request.assert_called_once()
        assert context.results["s1"]["status"] == "PASSED"
