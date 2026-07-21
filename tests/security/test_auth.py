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