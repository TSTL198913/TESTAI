"""BUG-095: AlertManager对象引用泄露 - get_alerts返回AlertRecord对象引用，可能导致内存泄漏。

源码位置: src/governance/monitoring.py:193-207

根因:
1. get_alerts返回AlertRecord对象的列表
2. 调用方持有这些对象引用，导致AlertManager内部的_alerts列表无法释放
3. AlertRecord对象包含details等可能很大的字典，长期持有会造成内存压力

修复方案:
- get_alerts返回dict列表而非AlertRecord对象列表
- 使用to_dict()方法转换，消除对象引用
- 确保调用方使用字典访问而非对象属性访问
"""
import pytest
import gc
import weakref

from src.governance.monitoring import AlertManager, AlertLevel, AlertRecord


class TestAlertManagerReferenceLeak:
    """AlertManager对象引用泄露测试"""

    def test_get_alerts_returns_dict_not_objects(self):
        """get_alerts返回字典而非AlertRecord对象"""
        manager = AlertManager()
        manager.create_alert(AlertLevel.WARNING, "Test message", "test-component")
        
        alerts = manager.get_alerts()
        
        assert isinstance(alerts, list)
        for alert in alerts:
            assert isinstance(alert, dict), f"Expected dict, got {type(alert)}"
            assert "alert_id" in alert
            assert "level" in alert
            assert "message" in alert

    def test_get_alerts_dict_keys_match_to_dict(self):
        """返回的字典键与to_dict()一致"""
        manager = AlertManager()
        alert = manager.create_alert(
            AlertLevel.ERROR, 
            "Test error", 
            "test-component",
            trace_id="trace-123",
            details={"key": "value"}
        )
        
        alerts = manager.get_alerts()
        assert len(alerts) >= 1
        
        alert_dict = alerts[0]
        expected_keys = {"alert_id", "level", "message", "component", "trace_id", "details", "created_at", "acknowledged"}
        
        assert set(alert_dict.keys()) == expected_keys
        assert alert_dict["alert_id"] == alert.alert_id
        assert alert_dict["level"] == alert.level
        assert alert_dict["message"] == alert.message
        assert alert_dict["trace_id"] == "trace-123"
        assert alert_dict["details"] == {"key": "value"}

    def test_no_object_reference_leak(self):
        """验证get_alerts返回的是字典副本，不是对象引用"""
        manager = AlertManager()
        alert = manager.create_alert(AlertLevel.WARNING, "Leak test", "test")
        
        alerts = manager.get_alerts()
        
        alert_dict = alerts[0]
        alert_dict["message"] = "Modified"
        
        original_alerts = manager.get_alerts()
        
        assert original_alerts[0]["message"] == "Leak test", "Original alert should not be modified"
        assert alert_dict["message"] == "Modified", "Returned dict should be independent copy"

    def test_get_alerts_by_level_returns_dict(self):
        """按级别查询也返回字典"""
        manager = AlertManager()
        manager.create_alert(AlertLevel.WARNING, "Warning", "test")
        manager.create_alert(AlertLevel.ERROR, "Error", "test")
        
        warnings = manager.get_alerts(level=AlertLevel.WARNING)
        
        assert isinstance(warnings, list)
        for w in warnings:
            assert isinstance(w, dict)
            assert w["level"] == AlertLevel.WARNING

    def test_get_alerts_acknowledged_filter_returns_dict(self):
        """按确认状态过滤也返回字典"""
        manager = AlertManager()
        alert = manager.create_alert(AlertLevel.WARNING, "Test", "test")
        manager.acknowledge_alert(alert.alert_id)
        
        acknowledged = manager.get_alerts(acknowledged=True)
        
        assert isinstance(acknowledged, list)
        for a in acknowledged:
            assert isinstance(a, dict)
            assert a["acknowledged"] is True

    def test_alert_dict_is_serializable(self):
        """返回的字典可序列化"""
        import json
        
        manager = AlertManager()
        manager.create_alert(
            AlertLevel.ERROR, 
            "Serializable test", 
            "test",
            details={"nested": {"key": ["value1", "value2"]}}
        )
        
        alerts = manager.get_alerts()
        alert_dict = alerts[0]
        
        json_str = json.dumps(alert_dict)
        parsed = json.loads(json_str)
        
        assert parsed["message"] == "Serializable test"
        assert parsed["details"]["nested"]["key"] == ["value1", "value2"]