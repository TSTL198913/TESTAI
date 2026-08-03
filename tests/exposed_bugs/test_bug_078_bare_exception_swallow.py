import pytest
from unittest.mock import patch, MagicMock
from src.security.auth import PasswordHasher


class TestBareExceptionSwallow:
    def test_password_verify_exception_hidden(self):
        """测试密码验证异常被吞没，无法区分真正的认证失败"""
        hasher = PasswordHasher()

        with patch("src.security.auth.bcrypt.checkpw", side_effect=RuntimeError("bcrypt internal error")):
            result = hasher.verify_password("password", "invalid_hash")

            assert result is False, "Should return False on bcrypt error"

            result2 = hasher.verify_password("wrong_password", "valid_hash_format")

            assert result2 is False, "Should return False on wrong password"

            assert result == result2, \
                "Cannot distinguish between bcrypt error and wrong password - security concern"
