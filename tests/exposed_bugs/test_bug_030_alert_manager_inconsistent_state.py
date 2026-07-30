import pytest
import json
from unittest.mock import patch, MagicMock
from src.monitoring.alert_manager import AlertManager, AlertLevel, AlertType


class TestAlertManagerInconsistentState:
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=MagicMock)
    def test_load_alerts_corrupt_file_cleans_both_alerts_and_rules(self, mock_open, mock_exists):
        """边界：加载损坏的alerts文件时应同时清理alerts和rules"""
        mock_exists.return_value = True
        
        def mock_read(*args, **kwargs):
            raise json.JSONDecodeError("Invalid JSON", "", 0)
        
        mock_open.return_value.__enter__.return_value.read = mock_read
        
        manager = AlertManager(storage_path="test_alerts.json")
        
        assert len(manager.alerts) == 0, "alerts应被清空"
        assert len(manager.rules) == 0, (
            "BUG-030: 加载损坏文件时rules未被清空，导致状态不一致"
        )

    @patch("os.path.exists")
    def test_load_alerts_missing_file_initializes_both(self, mock_exists):
        """正向：加载不存在的文件时应正确初始化alerts和rules"""
        mock_exists.return_value = False
        
        manager = AlertManager(storage_path="test_alerts.json")
        
        assert len(manager.alerts) == 0, "alerts应初始化为空列表"
        assert len(manager.rules) > 0, "rules应包含默认规则"