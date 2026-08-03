"""P0-6: HttpOnly Cookie 认证测试。

验证:
1. 登录响应设置 HttpOnly + Secure + SameSite=Strict 的 cookie
2. 受保护端点可读 cookie 认证
3. logout 清除 cookie
4. Authorization header 兼容期仍可用
5. cookie 优先于 header
"""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

from src.platform.api import app


@pytest.fixture(autouse=True)
def dev_cookie_insecure(monkeypatch):
    """测试环境:COOKIE_SECURE=false 以便 TestClient(HTTP)能发送 cookie。

    生产环境 cookie 是 Secure,仅 HTTPS 可发送;TestClient 用 HTTP,
    需关闭 Secure 标志才能测试 cookie 回传。
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    yield


@pytest.fixture
def client_no_rate_limit():
    """重置 rate limit 的 client。"""
    from src.platform.api import token_manager
    token_manager._login_attempts.clear()
    with TestClient(app) as c:
        yield c


def test_login_sets_httponly_cookie(client_no_rate_limit):
    """登录成功后必须设置 HttpOnly + SameSite=Strict cookie。"""
    response = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert response.status_code == 200

    # 检查 Set-Cookie 头
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) >= 2, (
        f"登录响应必须设置 access_token 和 refresh_token 两个 cookie, "
        f"实际 Set-Cookie 数量: {len(set_cookie_headers)}"
    )

    # 合并所有 Set-Cookie 内容用于断言
    all_cookies = " ".join(set_cookie_headers).lower()
    assert "access_token=" in all_cookies, "必须设置 access_token cookie"
    assert "refresh_token=" in all_cookies, "必须设置 refresh_token cookie"
    assert "httponly" in all_cookies, (
        f"cookie 必须标记 HttpOnly(防止 JS 读取), 实际: {set_cookie_headers}"
    )
    assert "samesite=strict" in all_cookies, (
        f"cookie 必须标记 SameSite=Strict(防 CSRF), 实际: {set_cookie_headers}"
    )


def test_login_cookie_secure_flag_in_production(monkeypatch):
    """生产环境 cookie 必须有 Secure 标志。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    monkeypatch.setenv("DEFAULT_USER_PASSWORD", "ProdPass123!")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")

    orig_api = sys.modules.get("src.platform.api")
    orig_auth = sys.modules.get("src.security.auth")

    try:
        for mod in list(sys.modules.keys()):
            if mod == "src.platform.api" or mod == "src.security.auth":
                del sys.modules[mod]
        api_module = importlib.import_module("src.platform.api")

        api_module.token_manager._login_attempts.clear()
        with TestClient(api_module.app) as c:
            response = c.post(
                "/auth/login",
                json={"username": "admin", "password": "ProdPass123!"},
            )
            assert response.status_code == 200
            set_cookie_headers = response.headers.get_list("set-cookie")
            all_cookies = " ".join(set_cookie_headers).lower()
            assert "secure" in all_cookies, (
                f"生产环境 cookie 必须有 Secure 标志, 实际: {set_cookie_headers}"
            )
    finally:
        if orig_auth is not None:
            sys.modules["src.security.auth"] = orig_auth
            import src.security
            src.security.auth = orig_auth
        elif "src.security.auth" in sys.modules:
            del sys.modules["src.security.auth"]
            import src.security
            if hasattr(src.security, "auth"):
                delattr(src.security, "auth")
        if orig_api is not None:
            sys.modules["src.platform.api"] = orig_api
            import src.platform
            src.platform.api = orig_api
        elif "src.platform.api" in sys.modules:
            del sys.modules["src.platform.api"]
            import src.platform
            if hasattr(src.platform, "api"):
                delattr(src.platform, "api")

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("DEFAULT_USER_PASSWORD", raising=False)
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)


def test_authenticated_route_reads_cookie(client_no_rate_limit):
    """受保护端点必须能从 cookie 读取认证信息。"""
    # 登录获取 cookie
    login_resp = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200

    # 用 cookie 访问受保护端点(不带 Authorization header)
    response = client_no_rate_limit.get("/auth/me")
    assert response.status_code == 200, (
        f"带 cookie 访问受保护端点应成功, 实际: {response.status_code}, body: {response.text}"
    )
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == "admin"


def test_authorization_header_still_works_compatibility(client_no_rate_limit):
    """兼容期:Authorization header 仍可用于认证。"""
    # 登录获取 token
    login_resp = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    token = login_resp.json()["data"]["access_token"]

    # 清除 cookie,只用 header
    client_no_rate_limit.cookies.clear()
    response = client_no_rate_limit.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, (
        f"Authorization header 兼容期应可用, 实际: {response.status_code}"
    )


def test_cookie_takes_precedence_over_header(client_no_rate_limit):
    """cookie 与 header 同时存在时,cookie 优先(若 cookie 有效)。"""
    # 用户 A 登录获取 cookie
    login_a = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_a.status_code == 200

    # 用户 B 登录获取 token(用 header 传)
    login_b = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "tester", "password": "password"},
    )
    token_b = login_b.json()["data"]["access_token"]

    # 当前 cookie 是 admin(最后登录的会覆盖,需重新登录 admin)
    client_no_rate_limit.cookies.clear()
    login_a2 = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_a2.status_code == 200

    # cookie 是 admin,header 是 tester,应优先 cookie(admin)
    response = client_no_rate_limit.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == "admin", (
        f"cookie 应优先于 Authorization header, 实际: {response.json()['data']['username']}"
    )


def test_logout_clears_cookie(client_no_rate_limit):
    """logout 端点必须清除认证 cookie。"""
    # 登录
    login_resp = client_no_rate_limit.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200

    # logout
    logout_resp = client_no_rate_limit.post("/auth/logout")
    assert logout_resp.status_code == 200

    # logout 后 cookie 应被清除(Max-Age=0 或 expires 过期)
    set_cookie_headers = logout_resp.headers.get_list("set-cookie")
    all_cookies = " ".join(set_cookie_headers).lower()
    # delete_cookie 会设置 Max-Age=0 或 expires=过去时间
    assert "max-age=0" in all_cookies or "expires=" in all_cookies, (
        f"logout 应清除 cookie(Max-Age=0 或 expires 过期), 实际: {set_cookie_headers}"
    )


def test_no_token_returns_401(client_no_rate_limit):
    """无 token(无 cookie 无 header)访问受保护端点返回 401。"""
    # 确保无 cookie
    client_no_rate_limit.cookies.clear()
    response = client_no_rate_limit.get("/auth/me")
    assert response.status_code == 401, (
        f"无认证信息应返回 401, 实际: {response.status_code}"
    )


def test_invalid_cookie_returns_401(client_no_rate_limit):
    """无效 cookie 返回 401。"""
    client_no_rate_limit.cookies.set("access_token", "invalid.token.here")
    response = client_no_rate_limit.get("/auth/me")
    assert response.status_code == 401
