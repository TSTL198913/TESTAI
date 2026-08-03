"""
API 工具函数与请求模型单元测试
覆盖:
1. _compute_cors_origins 环境变量处理
2. _cookie_secure Cookie 安全标志
3. CreateUserRequest / CreateTeamRequest 验证逻辑
4. get_current_user_from_cookie 认证逻辑
5. require_permission 权限校验

注意: 使用 patch.object(api, ...) 而非 patch("src.platform.api.xxx")
原因: test_api_security 等测试会删除/重建 src.platform.api 模块,
     导致 sys.modules['src.platform.api'] 与本地 import 的 api 引用不一致。
     patch.object 直接操作本地引用, 确保一致性。
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.platform import api


# ==================== _compute_cors_origins ====================

class TestComputeCorsOrigins:
    """测试 CORS 源计算逻辑"""

    def test_custom_origins_from_env(self, monkeypatch):
        """CORS_ALLOWED_ORIGINS 环境变量设置时, 使用自定义源"""
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.com, https://b.com")
        monkeypatch.setenv("ENVIRONMENT", "development")
        result = api._compute_cors_origins()
        assert result == ["https://a.com", "https://b.com"]

    def test_empty_origins_in_production_raises_error(self, monkeypatch):
        """生产环境未设 CORS_ALLOWED_ORIGINS 时应抛 RuntimeError"""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
            api._compute_cors_origins()

    def test_default_origins_in_development(self, monkeypatch):
        """开发环境使用默认源 (不含通配符)"""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        result = api._compute_cors_origins()
        assert "http://localhost:3000" in result
        assert "http://localhost:8080" in result
        assert "*" not in result

    def test_empty_strings_in_csv_ignored(self, monkeypatch):
        """CORS_ALLOWED_ORIGINS 中的空字符串应被忽略"""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ",https://a.com, ,https://b.com,")
        result = api._compute_cors_origins()
        assert "https://a.com" in result
        assert "https://b.com" in result
        assert "" not in result


# ==================== _cookie_secure ====================

class TestCookieSecure:
    """测试 Cookie 安全标志"""

    def test_production_environment(self, monkeypatch):
        """生产环境 Cookie 必须 Secure"""
        monkeypatch.setenv("ENVIRONMENT", "production")
        result = api._cookie_secure()
        assert result is True

    def test_development_default(self, monkeypatch):
        """开发环境 Cookie 默认不 Secure"""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        result = api._cookie_secure()
        assert result is False

    def test_development_with_cookie_secure_true(self, monkeypatch):
        """开发环境可显式设 Cookie 为 Secure"""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("COOKIE_SECURE", "true")
        result = api._cookie_secure()
        assert result is True


# ==================== CreateUserRequest ====================

class TestCreateUserRequest:
    """测试用户创建请求验证"""

    def test_valid_email(self):
        """合法邮箱应通过验证"""
        from src.platform.api import CreateUserRequest
        req = CreateUserRequest(
            username="testuser",
            email="test@example.com",
            password="Password123!",
            role="tester",
        )
        assert req.email == "test@example.com"

    def test_invalid_email_no_at(self):
        """无 @ 的邮箱应抛验证错误"""
        from src.platform.api import CreateUserRequest
        with pytest.raises(Exception):
            CreateUserRequest(
                username="testuser",
                email="invalid-email",
                password="Password123!",
                role="tester",
            )

    def test_invalid_email_no_domain(self):
        """无域名的邮箱应抛验证错误"""
        from src.platform.api import CreateUserRequest
        with pytest.raises(Exception):
            CreateUserRequest(
                username="testuser",
                email="test@",
                password="Password123!",
                role="tester",
            )


# ==================== CreateTeamRequest ====================

class TestCreateTeamRequest:
    """测试团队创建请求验证"""

    def test_valid_team_name(self):
        """合法团队名应通过验证"""
        from src.platform.api import CreateTeamRequest
        req = CreateTeamRequest(name="TestTeam", description="A test team")
        assert req.name == "TestTeam"

    def test_empty_name_raises_error(self):
        """空团队名应抛验证错误"""
        from src.platform.api import CreateTeamRequest
        with pytest.raises(Exception):
            CreateTeamRequest(name="", description="Empty team")

    def test_whitespace_name_raises_error(self):
        """纯空格团队名应抛验证错误"""
        from src.platform.api import CreateTeamRequest
        with pytest.raises(Exception):
            CreateTeamRequest(name="   ", description="Whitespace team")

    def test_long_name_raises_error(self):
        """超长团队名应抛验证错误"""
        from src.platform.api import CreateTeamRequest
        with pytest.raises(Exception):
            CreateTeamRequest(name="A" * 101, description="Too long")

    def test_name_is_stripped(self):
        """团队名应被 trim 空白"""
        from src.platform.api import CreateTeamRequest
        req = CreateTeamRequest(name="  TeamName  ", description="Trim test")
        assert req.name == "TeamName"


# ==================== get_current_user_from_cookie ====================

class TestGetCurrentUserFromCookie:
    def test_cookie_auth_success(self):
        """Cookie 认证成功: 优先使用 cookie 中的 token"""
        mock_request = MagicMock()
        mock_request.cookies = {"access_token": "valid_cookie_token"}

        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.username = "testuser"

        with patch.object(api, "token_manager") as mock_tm:
            mock_tm.verify_token.return_value = mock_user

            user = api.get_current_user_from_cookie(
                request=mock_request,
                credentials=None,
            )

            assert user == mock_user
            mock_tm.verify_token.assert_called_once_with("valid_cookie_token")

    def test_header_fallback_when_no_cookie(self):
        """无 cookie 时回退到 Authorization header"""
        mock_request = MagicMock()
        mock_request.cookies = {}

        mock_credentials = MagicMock()
        mock_credentials.credentials = "valid_header_token"

        mock_user = MagicMock()
        mock_user.id = "user-2"

        with patch.object(api, "token_manager") as mock_tm:
            mock_tm.verify_token.return_value = mock_user

            user = api.get_current_user_from_cookie(
                request=mock_request,
                credentials=mock_credentials,
            )

            assert user == mock_user
            mock_tm.verify_token.assert_called_once_with("valid_header_token")

    def test_both_cookie_and_header(self):
        """两者都有时, 优先 cookie"""
        mock_request = MagicMock()
        mock_request.cookies = {"access_token": "cookie_token"}

        mock_credentials = MagicMock()
        mock_credentials.credentials = "header_token"

        cookie_user = MagicMock()
        cookie_user.id = "cookie-user"

        with patch.object(api, "token_manager") as mock_tm:
            mock_tm.verify_token.return_value = cookie_user

            user = api.get_current_user_from_cookie(
                request=mock_request,
                credentials=mock_credentials,
            )

            assert user.id == "cookie-user"
            mock_tm.verify_token.assert_called_once_with("cookie_token")

    def test_no_token_raises_401(self):
        """无 token 时应抛出 HTTPException (401)"""
        from fastapi import HTTPException
        mock_request = MagicMock()
        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            api.get_current_user_from_cookie(
                request=mock_request,
                credentials=None,
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired" in str(exc_info.value.detail)

    def test_invalid_cookie_token(self):
        """Cookie token 无效时, 回退到 header"""
        mock_request = MagicMock()
        mock_request.cookies = {"access_token": "invalid_cookie"}

        mock_credentials = MagicMock()
        mock_credentials.credentials = "valid_header"

        header_user = MagicMock()
        header_user.id = "header-user"

        with patch.object(api, "token_manager") as mock_tm:
            mock_tm.verify_token.side_effect = [None, header_user]

            user = api.get_current_user_from_cookie(
                request=mock_request,
                credentials=mock_credentials,
            )

            assert user.id == "header-user"


# ==================== require_permission ====================

class TestRequirePermission:
    def test_permission_granted(self):
        """权限校验通过"""
        from src.security.permissions import Permission
        mock_user = MagicMock()

        with patch.object(api, "permission_manager") as mock_pm:
            mock_pm.has_permission.return_value = True

            dependency = api.require_permission(Permission.VIEW_WORKFLOW)
            result = dependency(user=mock_user)

            assert result == mock_user
            mock_pm.has_permission.assert_called_once_with(
                mock_user, Permission.VIEW_WORKFLOW
            )

    def test_permission_denied(self):
        """权限不足应抛 403"""
        from fastapi import HTTPException
        from src.security.permissions import Permission
        mock_user = MagicMock()

        with patch.object(api, "permission_manager") as mock_pm:
            mock_pm.has_permission.return_value = False

            dependency = api.require_permission(Permission.VIEW_WORKFLOW)

            with pytest.raises(HTTPException) as exc_info:
                dependency(user=mock_user)

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)