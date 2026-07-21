"""
密码哈希和密钥管理测试
覆盖场景：正向、负向、边界、异常、依赖
"""
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.security.auth import (
    TokenManager, User, Role, PasswordHasher
)
from src.users.user_manager import UserManager, UserProfile, UserStatus


class TestPasswordHasher:
    """密码哈希工具测试"""

    # === 正向场景 ===
    def test_hash_password_returns_non_empty_string(self):
        """正向：哈希密码返回非空字符串"""
        hashed = PasswordHasher.hash_password("MySecurePassword123")
        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != "MySecurePassword123"

    def test_verify_correct_password(self):
        """正向：正确密码验证成功"""
        password = "TestPassword456"
        hashed = PasswordHasher.hash_password(password)
        assert PasswordHasher.verify_password(password, hashed) is True

    def test_hash_different_passwords_produce_different_hashes(self):
        """正向：不同密码产生不同哈希"""
        hash1 = PasswordHasher.hash_password("password1")
        hash2 = PasswordHasher.hash_password("password2")
        assert hash1 != hash2

    def test_same_password_produces_different_hashes_due_to_salt(self):
        """正向：相同密码因盐值不同产生不同哈希"""
        hash1 = PasswordHasher.hash_password("samepassword")
        hash2 = PasswordHasher.hash_password("samepassword")
        assert hash1 != hash2

    # === 负向场景 ===
    def test_verify_wrong_password(self):
        """负向：错误密码验证失败"""
        hashed = PasswordHasher.hash_password("correctpassword")
        assert PasswordHasher.verify_password("wrongpassword", hashed) is False

    def test_verify_empty_password(self):
        """负向：空密码验证失败"""
        hashed = PasswordHasher.hash_password("somepassword")
        assert PasswordHasher.verify_password("", hashed) is False

    def test_verify_password_against_empty_hash(self):
        """负向：密码与空哈希验证失败"""
        assert PasswordHasher.verify_password("anypassword", "") is False

    def test_verify_password_against_invalid_hash_format(self):
        """异常：无效哈希格式验证失败"""
        assert PasswordHasher.verify_password("password", "invalid_hash_format") is False

    # === 边界场景 ===    def test_hash_empty_password_returns_empty(self):
        """边界：空密码返回空字符串"""
        assert PasswordHasher.hash_password("") == ""

    def test_hash_very_long_password(self):
        """边界：超长密码（1000字符）能正常哈希和验证"""
        long_password = "a" * 1000
        hashed = PasswordHasher.hash_password(long_password)
        assert PasswordHasher.verify_password(long_password, hashed) is True

    def test_hash_unicode_password(self):
        """边界：Unicode密码能正常哈希和验证"""
        unicode_password = "密码🔐Password123"
        hashed = PasswordHasher.hash_password(unicode_password)
        assert PasswordHasher.verify_password(unicode_password, hashed) is True

    # === 依赖场景 ===
    def test_pbkdf2_format_verification(self):
        """依赖：PBKDF2哈希格式正确（当bcrypt不可用时）"""
        with patch("src.security.auth.BCRYPT_AVAILABLE", False):
            hashed = PasswordHasher.hash_password("testpassword")
            assert hashed.startswith("pbkdf2$")
            parts = hashed.split("$")
            assert len(parts) == 4
            assert parts[0] == "pbkdf2"
            assert int(parts[1]) >= 100000
            assert len(parts[2]) > 0
            assert len(parts[3]) > 0

    def test_pbkdf2_verification_works(self):
        """依赖：PBKDF2哈希能正确验证"""
        with patch("src.security.auth.BCRYPT_AVAILABLE", False):
            password = "pbkdf2testpassword"
            hashed = PasswordHasher.hash_password(password)
            assert hashed.startswith("pbkdf2$")
            assert PasswordHasher.verify_password(password, hashed) is True
            assert PasswordHasher.verify_password("wrong", hashed) is False


class TestTokenManagerSecretKey:
    """密钥管理测试"""

    # === 正向场景 ===
    def test_secret_key_from_environment_variable(self):
        """正向：从环境变量获取密钥"""
        with patch.dict(os.environ, {"SECRET_KEY": "a" * 64}):
            manager = TokenManager()
            assert manager.secret_key == "a" * 64

    def test_secret_key_from_jwt_secret_key_env(self):
        """正向：从JWT_SECRET_KEY环境变量获取密钥"""
        with patch.dict(os.environ, {"SECRET_KEY": "", "JWT_SECRET_KEY": "b" * 64}):
            manager = TokenManager()
            assert manager.secret_key == "b" * 64

    def test_secret_key_from_constructor_param(self):
        """正向：从构造函数参数获取密钥"""
        manager = TokenManager(secret_key="explicit_key_" + "x" * 32)
        assert manager.secret_key == "explicit_key_" + "x" * 32

    def test_generated_key_is_64_chars(self):
        """正向：生成密钥长度为64字符（32字节）"""
        with patch.dict(os.environ, {}, clear=True):
            if "SECRET_KEY" in os.environ:
                del os.environ["SECRET_KEY"]
            if "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]
            manager = TokenManager()
            assert len(manager.secret_key) >= 64

    # === 负向场景 ===
    def test_no_secret_key_generates_temporary_key(self):
        """负向：无密钥环境变量时生成临时密钥"""
        with patch.dict(os.environ, {}, clear=True):
            if "SECRET_KEY" in os.environ:
                del os.environ["SECRET_KEY"]
            if "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]
            manager = TokenManager()
            assert len(manager.secret_key) >= 64

    # === 边界场景 ===
    def test_short_secret_key_raises_error(self):
        """边界：短密钥必须抛出异常"""
        with pytest.raises(ValueError, match="must be at least 32 bytes"):
            TokenManager(secret_key="short")

    # === 依赖场景 ===
    def test_token_generated_with_env_key_can_be_verified(self):
        """依赖：使用环境变量密钥生成的token能被验证"""
        with patch.dict(os.environ, {"SECRET_KEY": "c" * 64}):
            manager = TokenManager()
            user = User(id="1", username="admin", email="a@t.com", role=Role.ADMIN)
            token = manager.create_access_token(user)
            verified = manager.verify_token(token)
            assert verified is not None
            assert verified.username == "admin"


class TestTokenManagerPasswordAuth:
    """认证模块密码哈希集成测试"""

    # === 正向场景 ===
    def test_authenticate_with_default_password(self):
        """正向：使用默认密码认证成功"""
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        user = manager.authenticate("admin", "password")
        assert user is not None
        assert user.username == "admin"

    def test_authenticate_with_custom_default_password(self):
        """正向：使用自定义默认密码认证成功"""
        with patch.dict(os.environ, {"DEFAULT_USER_PASSWORD": "CustomPass123"}):
            manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
            user = manager.authenticate("admin", "CustomPass123")
            assert user is not None
            assert user.username == "admin"

    # === 负向场景 ===
    def test_authenticate_wrong_password(self):
        """负向：错误密码认证失败"""
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        user = manager.authenticate("admin", "wrongpassword")
        assert user is None

    def test_authenticate_nonexistent_user(self):
        """负向：不存在用户认证失败"""
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        user = manager.authenticate("nonexistent", "password")
        assert user is None

    # === 依赖场景 ===
    def test_set_password_changes_auth(self):
        """依赖：设置密码后旧密码失效，新密码生效"""
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        manager.set_password("admin", "NewPassword789")

        assert manager.authenticate("admin", "password") is None
        assert manager.authenticate("admin", "NewPassword789") is not None

    def test_password_hash_not_stored_in_plaintext(self):
        """依赖：密码哈希不是明文"""
        manager = TokenManager(secret_key="test-secret-key-at-least-32-bytes-long!")
        stored_hash = manager.get_password_hash("admin")
        assert stored_hash != "password"
        assert len(stored_hash) > 0


class TestUserManagerDatabaseMode:
    """UserManager数据库模式测试"""

    def setup_method(self):
        """使用SQLite内存数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["SQLITE_PATH"] = self.db_path
        # 重置数据库管理器单例
        from src.storage.database import reset_db_manager
        reset_db_manager()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        if "SQLITE_PATH" in os.environ:
            del os.environ["SQLITE_PATH"]
        from src.storage.database import reset_db_manager
        reset_db_manager()

    # === 正向场景 ===
    def test_create_user_in_database_mode(self):
        """正向：数据库模式下创建用户"""
        manager = UserManager(use_database=True)
        user = manager.create_user(
            username="dbuser",
            email="db@example.com",
            role=Role.TESTER,
            full_name="DB User",
            password="SecurePass123",
        )
        assert user.user_id is not None
        assert user.username == "dbuser"
        assert user.password_hash != ""
        assert user.password_hash != "SecurePass123"

    def test_verify_password_in_database_mode(self):
        """正向：数据库模式下验证密码"""
        manager = UserManager(use_database=True)
        manager.create_user(
            username="pwduser",
            email="pwd@example.com",
            role=Role.TESTER,
            password="MyPassword456",
        )
        assert manager.verify_password("pwduser", "MyPassword456") is True
        assert manager.verify_password("pwduser", "wrong") is False

    def test_set_password_in_database_mode(self):
        """正向：数据库模式下设置密码"""
        manager = UserManager(use_database=True)
        user = manager.create_user(
            username="setpwduser",
            email="setpwd@example.com",
            role=Role.TESTER,
        )
        assert manager.set_password(user.user_id, "NewPass789") is True
        assert manager.verify_password("setpwduser", "NewPass789") is True

    # === 负向场景 ===
    def test_duplicate_username_in_database_mode(self):
        """负向：数据库模式下重复用户名"""
        manager = UserManager(use_database=True)
        manager.create_user(username="dup", email="dup1@example.com", role=Role.TESTER)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username="dup", email="dup2@example.com", role=Role.TESTER)

    def test_set_password_nonexistent_user(self):
        """负向：为不存在的用户设置密码"""
        manager = UserManager(use_database=True)
        assert manager.set_password("nonexistent_id", "password") is False

    # === 边界场景 ===
    def test_database_fallback_to_json_on_error(self):
        """边界：数据库不可用时回退到JSON"""
        temp_dir = tempfile.mkdtemp()
        storage_path = os.path.join(temp_dir, "fallback_users.json")
        try:
            with patch("src.storage.database.get_db_manager", side_effect=Exception("DB error")):
                manager = UserManager(storage_path=storage_path, use_database=True)
                assert manager._use_database is False
                user = manager.create_user(
                    username="fallbackuser_unique",
                    email="fallback_unique@example.com",
                    role=Role.TESTER,
                )
                assert user.user_id is not None
                assert user.username == "fallbackuser_unique"
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    # === 依赖场景 ===
    def test_user_persistence_across_instances(self):
        """依赖：用户数据在不同UserManager实例间持久化"""
        manager1 = UserManager(use_database=True)
        manager1.create_user(
            username="persistuser",
            email="persist@example.com",
            role=Role.TESTER,
            password="PersistPass123",
        )

        # 创建新实例，应该能读取到之前的用户
        manager2 = UserManager(use_database=True)
        user = manager2.get_user_by_username("persistuser")
        assert user is not None
        assert user.email == "persist@example.com"
        assert manager2.verify_password("persistuser", "PersistPass123") is True
