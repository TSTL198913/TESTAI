"""BUG-064: Workflow API 响应格式不一致 - /config 端点不返回统一的 ApiResponse 格式。

源码位置: src/platform/api.py:648-655

根因:
1. 第654-655行直接返回 config_manager 的原始结果，未使用 ApiResponse 包装
2. 其他端点都使用 ApiResponse 统一格式 {success, data, message, error_code}
3. 前端需要统一的响应格式处理

正确行为:
- /config GET 端点应返回 ApiResponse 格式
"""
import pytest
import os
import tempfile
import json

from src.platform.config_manager import ConfigManager


class TestWorkflowApiResponseFormat:
    """API响应格式一致性测试"""

    def test_config_manager_get_all_returns_raw_dict(self):
        """ConfigManager.get_all() 返回原始dict而非ApiResponse格式"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config.json")
            with open(config_file, "w") as f:
                json.dump({
                    "api": {"host": "localhost", "port": 8000},
                    "database": {"url": "sqlite:///test.db"}
                }, f)
            
            os.environ["TESTAI_CONFIG_FILE"] = config_file
            
            cm = ConfigManager(config_file=config_file)
            result = cm.get_all()
            
            assert "success" not in result, (
                f"Expected 'success' key to NOT be present (demonstrating API bug), "
                f"but got: {result}"
            )
            assert "message" not in result, (
                f"Expected 'message' key to NOT be present (demonstrating API bug), "
                f"but got: {result}"
            )
            assert "error_code" not in result, (
                f"Expected 'error_code' key to NOT be present (demonstrating API bug), "
                f"but got: {result}"
            )

    def test_config_manager_get_section_returns_raw_dict(self):
        """ConfigManager.get_section() 返回原始dict而非ApiResponse格式"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config.json")
            with open(config_file, "w") as f:
                json.dump({
                    "api": {
                        "data": {"host": "localhost", "port": 8000},
                        "description": "API settings",
                        "readonly": False
                    }
                }, f)
            
            os.environ["TESTAI_CONFIG_FILE"] = config_file
            
            cm = ConfigManager(config_file=config_file)
            result = cm.get_section("api")
            
            assert "success" not in result, (
                f"Expected 'success' key to NOT be present (demonstrating API bug), "
                f"but got: {result}"
            )
            assert "host" in result
            assert "port" in result

    def test_api_response_model_has_required_fields(self):
        """ApiResponse模型应包含必要字段"""
        from src.platform.api import ApiResponse
        
        response = ApiResponse(
            success=True,
            data={"key": "value"},
            message="Test message",
        )
        
        assert hasattr(response, "success")
        assert hasattr(response, "data")
        assert hasattr(response, "message")
        assert hasattr(response, "error_code")
        
        response_dict = response.model_dump()
        assert "success" in response_dict
        assert "data" in response_dict
        assert "message" in response_dict
        assert "error_code" in response_dict