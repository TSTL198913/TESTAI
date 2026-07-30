import pytest
import jwt
from datetime import datetime, timedelta
from src.security.auth import TokenManager, PasswordHasher, Role, User


class TestAuthTokenSecurity:
    def test_decode_token_returns_none_on_invalid(self):
        manager = TokenManager()
        
        invalid_token = "invalid.token.string"
        result = manager.decode_token(invalid_token)
        
        assert result is None

    def test_verify_token_rejects_refresh_token(self):
        manager = TokenManager()
        user = User(id="1", username="testuser", email="test@testai.com", role=Role.TESTER)
        manager.users["testuser"] = user
        
        refresh_token = manager.create_refresh_token(user)
        
        result = manager.verify_token(refresh_token)
        
        assert result is None, "Refresh token should not be accepted as access token"

    def test_refresh_token_rejects_access_token(self):
        manager = TokenManager()
        user = User(id="1", username="testuser", email="test@testai.com", role=Role.TESTER)
        manager.users["testuser"] = user
        
        access_token = manager.create_access_token(user)
        
        result = manager.refresh_token(access_token)
        
        assert result is None, "Access token should not be accepted as refresh token"

    def test_empty_password_hash_returns_false(self):
        result = PasswordHasher.verify_password("password", "")
        
        assert result is False

    def test_empty_password_returns_false(self):
        hashed = PasswordHasher.hash_password("password")
        result = PasswordHasher.verify_password("", hashed)
        
        assert result is False

    def test_invalid_password_format_rejected(self):
        result = PasswordHasher.verify_password("password", "invalid_hash_format")
        
        assert result is False

    def test_login_rate_limit_triggers(self):
        manager = TokenManager()
        
        for _ in range(6):
            manager.authenticate("admin", "wrong_password")
        
        is_limited = manager.is_rate_limited("admin")
        
        assert is_limited is True, "Login should be rate limited after 5 failed attempts"