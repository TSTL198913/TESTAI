import pytest
from unittest.mock import patch
from src.engine.registry import get_pipeline


class TestRegistrySilentSkip:
    def test_get_pipeline_raises_on_unknown_processor(self):
        """负向：get_pipeline应在遇到未知处理器时抛出错误"""
        with pytest.raises(ValueError):
            get_pipeline(["http", "unknown_processor", "assertion"])

    def test_get_pipeline_with_valid_processors(self):
        """正向：get_pipeline应能创建有效的处理器列表"""
        processors = get_pipeline(["http", "assertion"])
        
        assert len(processors) == 2
        assert processors[0].__class__.__name__ == "HTTPProcessor"
        assert processors[1].__class__.__name__ == "AssertionProcessor"

    def test_get_pipeline_with_request_alias(self):
        """边界：get_pipeline应将'request'别名转换为'http'并发出警告"""
        with patch("src.engine.registry.warnings") as mock_warnings:
            processors = get_pipeline(["request"])
            
            mock_warnings.warn.assert_called_once()
            assert len(processors) == 1
            assert processors[0].__class__.__name__ == "HTTPProcessor"

    def test_get_pipeline_with_empty_config(self):
        """边界：空配置应返回空处理器列表"""
        processors = get_pipeline([])
        
        assert len(processors) == 0