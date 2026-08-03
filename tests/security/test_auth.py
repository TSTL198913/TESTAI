import pytest
import jwt
from datetime import datetime, timedelta

from src.security.auth import TokenManager, User, Role


class TestRole:
    def test_role_enum_values(self):
        assert Role.ADMIN.value == "admin"
        assert Role.TESTER.value == "tester"
        assert Role.VIEWER.value == "viewer"
        assert Role.GUEST.value == "guest"


class TestUser:
    def test_user_creation(self):
        user = User(id="1", username="testuser", email="test@testai.com", role=Role.ADMIN)
        assert user.id == "1"
        assert user.username == "testuser"
        assert user.email == "test@testai.com"
        assert user.role == Role.ADMIN
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)

    def test_user_with_last_login(self):
        last_login = datetime(2026, 7, 20, 10, 0, 0)
        user = User(id="1", username="testuser", email="test@testai.com", role=Role.ADMIN, last_login=last_login)
        assert user.last_login == last_login


class TestTokenManager:
    def test_create_access_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        token = manager.create_access_token(user)
        assert isinstance(token, str)
        assert len(token) > 100
        assert "." in token

    def test_create_refresh_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        token = manager.create_refresh_token(user)
        assert isinstance(token, str)
        assert len(token) > 100
        assert "." in token

    def test_decode_valid_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        token = manager.create_access_token(user)
        payload = manager.decode_token(token)
        
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        payload = manager.decode_token("invalid.token.here")
        assert payload is None

    def test_decode_expired_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        manager.access_token_expire_minutes = -1
        token = manager.create_access_token(user)
        
        payload = manager.decode_token(token)
        assert payload is None

    def test_verify_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        token = manager.create_access_token(user)
        verified_user = manager.verify_token(token)
        
        assert verified_user is not None
        assert verified_user.username == "admin"

    def test_verify_invalid_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        verified_user = manager.verify_token("invalid.token")
        assert verified_user is None

    def test_verify_refresh_token_as_access(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        refresh_token = manager.create_refresh_token(user)
        verified_user = manager.verify_token(refresh_token)
        
        assert verified_user is None

    def test_refresh_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        refresh_token = manager.create_refresh_token(user)
        new_access_token = manager.refresh_token(refresh_token)
        
        assert new_access_token is not None
        assert isinstance(new_access_token, str)

    def test_refresh_invalid_token(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        new_access_token = manager.refresh_token("invalid.token")
        assert new_access_token is None

    def test_authenticate_valid_credentials(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = manager.authenticate("admin", "password")
        
        assert user is not None
        assert user.username == "admin"
        assert user.role == Role.ADMIN

    def test_authenticate_invalid_username(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = manager.authenticate("nonexistent", "password")
        
        assert user is None

    def test_authenticate_invalid_password(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        user = manager.authenticate("admin", "wrongpassword")
        
        assert user is None

    def test_default_users_initialized(self):
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes!")
        
        assert "admin" in manager.users
        assert "tester" in manager.users
        assert "viewer" in manager.users
        
        admin = manager.users["admin"]
        assert admin.role == Role.ADMIN
        
        tester = manager.users["tester"]
        assert tester.role == Role.TESTER
        
        viewer = manager.users["viewer"]
        assert viewer.role == Role.VIEWER


# ============================================================================
# P0-5/P0-7: 生产环境安全强化测试（新增）
# ============================================================================

import importlib
import logging
import sys


def _reload_auth_module():
    """重新加载 src.security.auth 模块以应用环境变量变更。"""
    for mod in list(sys.modules.keys()):
        if mod == "src.security.auth":
            del sys.modules[mod]
    module = importlib.import_module("src.security.auth")
    import src.security
    src.security.auth = module
    return module


# ============ P0-7: JWT 密钥生产强制 ============

def test_secret_key_required_in_production(monkeypatch):
    """生产环境无 SECRET_KEY 时 TokenManager 初始化必须抛 ValueError。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager

    with pytest.raises(ValueError, match="SECRET_KEY"):
        TokenManager_cls()


def test_secret_key_short_key_rejected(monkeypatch):
    """短密钥(<32 字节)必须被拒绝。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    short_key = "a" * 16  # 16 字节,低于 32 字节阈值
    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager

    with pytest.raises(ValueError, match="32 bytes"):
        TokenManager_cls(secret_key=short_key)


def test_secret_key_dev_fallback_allowed(monkeypatch, caplog):
    """开发模式无 SECRET_KEY 时允许生成临时密钥 + 警告日志。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager

    with caplog.at_level(logging.WARNING):
        mgr = TokenManager_cls()
    # 临时密钥应已生成(64 字符 hex = 32 字节)
    assert len(mgr.secret_key) >= 64
    # 必须有警告日志
    assert any("SECRET_KEY" in record.message for record in caplog.records), (
        "开发模式生成临时密钥时必须输出警告日志"
    )


def test_secret_key_from_env(monkeypatch):
    """SECRET_KEY 环境变量正确读取。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    strong_key = "a" * 64  # 64 字节,超过 32 字节阈值
    monkeypatch.setenv("SECRET_KEY", strong_key)
    monkeypatch.setenv("DEFAULT_USER_PASSWORD", "ProdPass123!")

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager
    mgr = TokenManager_cls()
    assert mgr.secret_key == strong_key


def test_jwt_secret_key_alias(monkeypatch):
    """JWT_SECRET_KEY 作为 SECRET_KEY 的别名。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    strong_key = "b" * 64
    monkeypatch.setenv("JWT_SECRET_KEY", strong_key)
    monkeypatch.setenv("DEFAULT_USER_PASSWORD", "ProdPass123!")

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager
    mgr = TokenManager_cls()
    assert mgr.secret_key == strong_key


# ============ P0-5: 默认密码生产强制 ============

def test_default_password_required_in_production(monkeypatch):
    """生产环境无 DEFAULT_USER_PASSWORD 时初始化必须抛 ValueError。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEFAULT_USER_PASSWORD", raising=False)
    # 提供强 SECRET_KEY 以通过密钥校验
    monkeypatch.setenv("SECRET_KEY", "a" * 64)

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager

    with pytest.raises(ValueError, match="DEFAULT_USER_PASSWORD"):
        TokenManager_cls()


def test_default_password_from_env(monkeypatch):
    """DEFAULT_USER_PASSWORD 环境变量生效,可用该密码登录。"""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    custom_password = "StrongProdPass123!"
    monkeypatch.setenv("DEFAULT_USER_PASSWORD", custom_password)

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager
    mgr = TokenManager_cls()

    # 用环境变量中的密码应可认证 admin 用户
    user = mgr.authenticate("admin", custom_password)
    assert user is not None, (
        f"使用 DEFAULT_USER_PASSWORD='{custom_password}' 应可登录 admin, "
        f"实际 authenticate 返回 None"
    )
    assert user.username == "admin"


def test_default_password_dev_fallback(monkeypatch):
    """开发模式无 DEFAULT_USER_PASSWORD 时使用 'password' 默认。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DEFAULT_USER_PASSWORD", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    auth_module = _reload_auth_module()
    TokenManager_cls = auth_module.TokenManager
    mgr = TokenManager_cls()

    # 开发默认 'password' 应可登录
    user = mgr.authenticate("admin", "password")
    assert user is not None, "开发模式 'password' 默认密码应可登录"
    assert user.username == "admin"