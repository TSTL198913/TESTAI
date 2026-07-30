import pytest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.ops.system_ops import SystemOperations
from src.security.auth import PasswordHasher


class TestBareExceptionSwallow:
    def test_audit_logs_not_cleared_on_partial_failure(self):
        """测试部分审计日志解析失败时不应清空所有日志"""
        valid_log = {
            "log_id": "test1",
            "user_id": "user1",
            "username": "testuser",
            "action": "create",
            "resource": "test_case",
            "resource_id": "wf1",
            "details": {},
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "error_message": "",
        }
        
        corrupted_log = {
            "log_id": "test2",
            "user_id": "user2",
            "username": "testuser",
            "action": "create", 
            "resource": "test_case",
            "resource_id": "wf2",
            "details": {},
            "timestamp": "invalid_datetime_format",
            "success": True,
            "error_message": "",
        }
        
        def mock_open_side_effect(*args, **kwargs):
            mock_file = MagicMock()
            filename = args[0]
            if "audit" in str(filename).lower():
                mock_file.read.return_value = json.dumps([valid_log, corrupted_log])
            elif "config" in str(filename).lower():
                mock_file.read.return_value = json.dumps({})
            mock_file.__enter__.return_value = mock_file
            return mock_file
        
        with patch("builtins.open", side_effect=mock_open_side_effect), \
             patch("os.path.exists", return_value=True):
            
            ops = SystemOperations()
            
            assert len(ops.audit_logs) == 1, \
                f"Expected 1 valid log, got {len(ops.audit_logs)}. Valid logs should not be cleared when one log is corrupted"

    def test_configs_not_cleared_on_partial_failure(self):
        """测试部分配置解析失败时不应清空所有配置"""
        ops = SystemOperations()
        
        valid_config = {
            "key": {"value": "test", "description": "", "category": "general",
                    "editable": True, "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()}
        }
        
        corrupted_config = {
            "bad_key": {"value": "test", "description": "", "category": "general",
                        "editable": True, "created_at": "invalid_datetime",
                        "updated_at": datetime.now().isoformat()}
        }
        
        with patch("builtins.open", MagicMock()) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = json.dumps({**valid_config, **corrupted_config})
            mock_open.return_value.__enter__.return_value = mock_file
            
            ops._load_configs()
            
            assert "key" in ops.configs, \
                "Valid configs should not be cleared when one config is corrupted"

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