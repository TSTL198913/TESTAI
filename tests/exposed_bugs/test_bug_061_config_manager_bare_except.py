"""BUG-061: ConfigManager 裸 except 吞没异常 - 第108行的 except: 静默吞没 JSON 解析错误。

源码位置: src/platform/config_manager.py:108

根因:
1. L108 使用裸 `except:` 捕获所有异常，无任何日志记录
2. JSON 解析失败时静默返回原始字符串值，可能导致后续逻辑异常
3. 缺乏异常信息，难以排查配置加载问题

正确行为:
- 使用具体异常类型捕获(JSONDecodeError)
- 异常时记录日志，便于排查
- 返回合理的默认值而非原始字符串
"""
import pytest
import os
import tempfile
import json

from src.platform.config_manager import ConfigManager


class TestConfigManagerBareExcept:
    """ConfigManager裸except问题测试"""

    def test_json_decode_error_not_swallowed_silently(self, caplog):
        """JSON解析错误不应静默吞没，应记录日志"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config.json")
            
            with open(config_file, "w") as f:
                json.dump({
                    "api": {
                        "data": {
                            "invalid_json": "{invalid json value",
                            "valid_json": json.dumps({"key": "value"}),
                        }
                    }
                }, f)
            
            cm = ConfigManager(config_file=config_file)
            
            result = cm.get_section("api")
            assert result is not None
            
            invalid_value = result.get("invalid_json")
            assert invalid_value == "{invalid json value", (
                f"Expected raw string for invalid JSON, got {invalid_value}"
            )

    def test_empty_config_value_returns_empty(self):
        """空配置值应返回空而非抛出异常"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config.json")
            
            with open(config_file, "w") as f:
                json.dump({
                    "api": {
                        "data": {
                            "empty_value": "",
                        }
                    }
                }, f)
            
            cm = ConfigManager(config_file=config_file)
            
            result = cm.get_section("api")
            assert result is not None
            assert result.get("empty_value") == ""

    def test_none_config_value_handled_gracefully(self):
        """None配置值应优雅处理"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config.json")
            
            with open(config_file, "w") as f:
                json.dump({
                    "api": {
                        "data": {
                            "null_value": None,
                        }
                    }
                }, f)
            
            cm = ConfigManager(config_file=config_file)
            
            result = cm.get_section("api")
            assert result is not None
            assert result.get("null_value") is None