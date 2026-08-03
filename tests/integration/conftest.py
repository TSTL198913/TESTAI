"""
集成测试环境守卫 + session 级共享 token

这些测试需要运行中的 API 服务器（默认 localhost:8000）和前端（localhost:3000）。
服务器不可达时自动跳过，避免将"环境不具备"误报为"测试失败"。

部署后冒烟测试：在 CI 部署完成后运行，验证真实服务可达性。
本地开发：自动跳过，不污染单元测试结果。

P0 修复 (429 碰撞隔离):
  旧版各测试文件自定义 module/class 级 auth_token fixture, 每个文件独立登录 admin。
  全量顺序运行时 admin 登录次数累计触发 5次/60秒 限流 (src/security/auth.py:221-237)
  → 后续测试 429 失败。test_rate_limiting 故意触发 429 更会锁定 admin 60 秒, 污染所有后续测试。

  解决:
    1. session 级 _session_login 只登录 1 次, 所有集成测试复用同一 token (auth_token /
       auth_headers / auth_tokens fixture)。
    2. test_rate_limiting 改用独立用户名 (rate_limit_isolated_user), 不污染 admin 计数。
    3. test_token_refresh_flow 改用 session 缓存的 refresh_token, 不重新登录。
"""
import os
import socket
import pytest
import requests

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
FRONT_BASE = os.environ.get("BASE_URL", "http://localhost:3000")


def _is_reachable(url: str, timeout: float = 1.0) -> bool:
    """检测目标 URL 是否可达（TCP 连通即可）。"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _api_healthy() -> bool:
    """检测 API 服务器 /health 端点是否正常响应。"""
    if not _is_reachable(API_BASE):
        return False
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_live_api():
    """会话级守卫：API 服务器不可达时跳过/失败整个集成测试套件。

    严格模式 (REQUIRE_INTEGRATION=1): 无 server 时直接 fail, 而非 skip。
    防止 CI "跳过即绿" —— 集成测试被 skip 仍报 success, 掩盖失效 (Gap 2 暴露:
    11 个 stale 测试因长期 skip 未被发现)。
    本地开发: 不设 REQUIRE_INTEGRATION → 维持 skip 行为 (不强求本地起 server)。
    """
    if not _api_healthy():
        msg = (
            f"集成测试需要运行中的 API 服务器 ({API_BASE}/health 不可达)。"
            "请先启动: uvicorn src.platform.api:app --port 8000"
        )
        # 严格模式: CI 应设置 REQUIRE_INTEGRATION=1, 无 server 直接失败 (禁止跳过即绿)
        if os.environ.get("REQUIRE_INTEGRATION", "").lower() in ("1", "true", "yes"):
            pytest.fail(f"[严格模式·禁止跳过即绿] {msg}", pytrace=False)
        pytest.skip(msg, allow_module_level=False)
    yield


# ==================== session 级共享 token (P0: 429 碰撞隔离) ====================

@pytest.fixture(scope="session")
def api_base_url(require_live_api):
    """session 级 API base URL, 替代旧版各文件 module 级 fixture。"""
    return API_BASE


@pytest.fixture(scope="session")
def _session_login(require_live_api):
    """session 级单次登录, 缓存 access_token + refresh_token + user。

    所有集成测试通过 auth_token / auth_headers / auth_tokens fixture 复用此缓存,
    全 session 仅登录 1 次 admin, 避免触发 5次/60秒 限流 (auth.py:232)。

    真实契约 (2026-08-02 实测): /auth/login 返回 JSON + Set-Cookie 双轨:
      - JSON data: {access_token, refresh_token, user}  (兼容旧客户端)
      - Set-Cookie: access_token / refresh_token HttpOnly  (防 XSS, P0-6 修复)
    此处取 JSON 字段, refresh_token 可用于 /auth/refresh 测试。
    """
    response = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": "admin", "password": "password"},
        timeout=10,
    )
    assert response.status_code == 200, (
        f"session 级 admin 登录失败: status={response.status_code}, body={response.text}"
    )
    data = response.json()
    assert data.get("success") is True, f"登录 success=False: {data}"
    assert "access_token" in data["data"], f"返回缺 access_token: {data['data'].keys()}"
    return data["data"]


@pytest.fixture(scope="session")
def auth_token(_session_login):
    """session 级共享 access_token, 所有集成测试复用, 替代旧版 module/class 级同名 fixture。"""
    return _session_login["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    """session 级共享 Authorization headers。"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def auth_tokens(_session_login):
    """session 级共享 tokens dict (兼容 test_full_stack_integration.auth_tokens 签名)。

    替代旧版 class 级 auth_tokens fixture (每次类加载都登录, 全量运行累计触发限流)。
    返回 {access_token, refresh_token, auth_headers} 三件套。
    """
    access = _session_login["access_token"]
    return {
        "access_token": access,
        "refresh_token": _session_login.get("refresh_token"),
        "auth_headers": {"Authorization": f"Bearer {access}"},
    }
