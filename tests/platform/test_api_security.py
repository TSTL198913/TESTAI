"""P0-1: CORS 配置安全测试。

验证:
1. 生产环境未设 CORS_ALLOWED_ORIGINS 启动失败
2. 环境变量配置生效
3. 开发模式使用默认源
4. CORS 中间件配置正确（非 ["*"]）
"""
import importlib
import os
import sys

import pytest


def _reload_api_module():
    """重新加载 src.platform.api 模块以应用环境变量变更。"""
    if "src.platform.api" in sys.modules:
        del sys.modules["src.platform.api"]
    return importlib.import_module("src.platform.api")


def test_cors_origins_from_env(monkeypatch):
    """CORS_ALLOWED_ORIGINS 环境变量配置生效。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.com,https://b.com")
    api_module = _reload_api_module()
    try:
        assert api_module._cors_allowed_origins == ["https://a.com", "https://b.com"]
    finally:
        _reload_api_module()  # 恢复


def test_cors_default_dev_origins(monkeypatch):
    """未设环境变量时使用开发默认源(不含通配符)。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    api_module = _reload_api_module()
    try:
        assert "*" not in api_module._cors_allowed_origins
        assert "http://localhost:3000" in api_module._cors_allowed_origins
        assert "http://localhost:8080" in api_module._cors_allowed_origins
    finally:
        _reload_api_module()


def test_cors_origins_restricted_in_production(monkeypatch):
    """生产环境未设 CORS_ALLOWED_ORIGINS 启动失败。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        _reload_api_module()
    # 恢复模块状态(避免污染后续测试)
    monkeypatch.setenv("ENVIRONMENT", "development")
    _reload_api_module()


def test_cors_middleware_not_wildcard():
    """CORS 中间件配置不能包含 "*" 通配符。"""
    from src.platform.api import app
    cors_middleware = None
    for mw in app.user_middleware:
        if "CORSMiddleware" in str(mw.cls):
            cors_middleware = mw
            break
    assert cors_middleware is not None, "CORSMiddleware 未注册"
    # allow_origins 不能是 ["*"]
    allow_origins = cors_middleware.kwargs.get("allow_origins")
    assert allow_origins != ["*"], (
        f"CORS allow_origins 不能是通配符 ['*'], 实际: {allow_origins}"
    )
    # allow_methods 不能是 ["*"]
    allow_methods = cors_middleware.kwargs.get("allow_methods")
    assert allow_methods != ["*"], (
        f"CORS allow_methods 不能是通配符 ['*'], 实际: {allow_methods}"
    )
    # allow_headers 不能是 ["*"]
    allow_headers = cors_middleware.kwargs.get("allow_headers")
    assert allow_headers != ["*"], (
        f"CORS allow_headers 不能是通配符 ['*'], 实际: {allow_headers}"
    )


def test_cors_methods_restricted():
    """CORS allow_methods 必须是显式方法列表。"""
    from src.platform.api import app
    cors_middleware = None
    for mw in app.user_middleware:
        if "CORSMiddleware" in str(mw.cls):
            cors_middleware = mw
            break
    allow_methods = cors_middleware.kwargs.get("allow_methods")
    expected_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"}
    assert set(allow_methods) == expected_methods, (
        f"CORS allow_methods 必须收窄为 {expected_methods}, 实际: {allow_methods}"
    )


def test_cors_headers_restricted():
    """CORS allow_headers 必须是显式 header 列表。"""
    from src.platform.api import app
    cors_middleware = None
    for mw in app.user_middleware:
        if "CORSMiddleware" in str(mw.cls):
            cors_middleware = mw
            break
    allow_headers = cors_middleware.kwargs.get("allow_headers")
    # 必须包含 Authorization 和 Content-Type
    assert "Authorization" in allow_headers, (
        f"CORS allow_headers 必须包含 Authorization, 实际: {allow_headers}"
    )
    assert "Content-Type" in allow_headers, (
        f"CORS allow_headers 必须包含 Content-Type, 实际: {allow_headers}"
    )
