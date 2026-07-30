"""BUG-012: AlertManager 无效输入未验证 - 空消息/空组件/无效级别。

源码位置: src/governance/monitoring.py:105-193 AlertManager

根因:
1. create_alert 未验证 message 和 component 是否为空字符串
2. 未验证 level 是否为有效级别(INFO/WARNING/ERROR/CRITICAL)
3. acknowledge_alert 对不存在的 alert_id 返回 False 而非抛出异常或记录警告
4. get_alerts 对无效 level 参数返回空列表而非报错
"""
import pytest

from src.governance.monitoring import AlertManager, AlertLevel


@pytest.fixture
def fresh_alert_manager():
    """创建干净的 AlertManager 实例。"""
    am = AlertManager()
    am._alerts = []
    return am


def test_create_alert_rejects_empty_message(fresh_alert_manager):
    """创建告警时消息不能为空。"""
    with pytest.raises(ValueError, match="消息不能为空"):
        fresh_alert_manager.create_alert(
            level=AlertLevel.ERROR,
            message="",
            component="test",
        )


def test_create_alert_rejects_empty_component(fresh_alert_manager):
    """创建告警时组件不能为空。"""
    with pytest.raises(ValueError, match="组件不能为空"):
        fresh_alert_manager.create_alert(
            level=AlertLevel.ERROR,
            message="test message",
            component="",
        )


def test_create_alert_rejects_invalid_level(fresh_alert_manager):
    """创建告警时级别必须有效。"""
    with pytest.raises(ValueError, match="无效级别"):
        fresh_alert_manager.create_alert(
            level="INVALID_LEVEL",
            message="test message",
            component="test",
        )


def test_acknowledge_nonexistent_alert_logs_warning(caplog, fresh_alert_manager):
    """确认不存在的告警时应记录警告日志。"""
    import logging
    caplog.set_level(logging.WARNING)
    
    result = fresh_alert_manager.acknowledge_alert("nonexistent-alert-id")
    
    assert result is False, "确认不存在的告警应返回 False"
    
    assert any("nonexistent-alert-id" in record.message for record in caplog.records), (
        f"确认不存在的告警时应记录警告日志,实际日志: {[r.message for r in caplog.records]}"
    )


def test_get_alerts_rejects_invalid_level(fresh_alert_manager):
    """查询告警时级别必须有效。"""
    fresh_alert_manager.create_alert(
        level=AlertLevel.INFO,
        message="test",
        component="test",
    )
    
    with pytest.raises(ValueError, match="无效级别"):
        fresh_alert_manager.get_alerts(level="INVALID_LEVEL")