import pytest

from src.governance.monitoring import (
    AlertLevel,
    AlertManager,
    AlertRecord,
    HealthMonitor,
    StructuredLogger,
)


class TestAlertLevel:
    def test_alert_levels(self):
        assert AlertLevel.INFO == "INFO"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.ERROR == "ERROR"
        assert AlertLevel.CRITICAL == "CRITICAL"


class TestAlertRecord:
    def test_alert_record_creation(self):
        alert = AlertRecord(
            alert_id="alert-1",
            level=AlertLevel.ERROR,
            message="Test error",
            component="test",
        )
        assert alert.alert_id == "alert-1"
        assert alert.level == AlertLevel.ERROR
        assert alert.message == "Test error"
        assert alert.component == "test"
        assert alert.acknowledged is False

    def test_alert_record_to_dict(self):
        alert = AlertRecord(
            alert_id="alert-1",
            level=AlertLevel.WARNING,
            message="Test warning",
            component="test",
            trace_id="trace-123",
            details={"key": "value"},
        )
        alert_dict = alert.to_dict()
        assert alert_dict["alert_id"] == "alert-1"
        assert alert_dict["level"] == AlertLevel.WARNING
        assert alert_dict["trace_id"] == "trace-123"
        assert alert_dict["details"] == {"key": "value"}


class TestStructuredLogger:
    def test_singleton_instance(self):
        logger1 = StructuredLogger()
        logger2 = StructuredLogger()
        assert logger1 is logger2

    def test_log_method(self):
        logger = StructuredLogger()
        record = logger.log("INFO", "Test message", key="value")
        assert record["message"] == "Test message"
        assert record["level"] == "INFO"
        assert record["key"] == "value"
        assert "timestamp" in record


class TestAlertManager:
    def test_singleton_instance(self):
        manager1 = AlertManager()
        manager2 = AlertManager()
        assert manager1 is manager2

    def test_create_alert(self):
        manager = AlertManager()
        alert = manager.create_alert(
            AlertLevel.ERROR,
            "Test error alert",
            "test-component",
            trace_id="trace-123",
            details={"test": "data"},
        )
        assert alert is not None
        assert alert.level == AlertLevel.ERROR
        assert alert.message == "Test error alert"
        assert alert.component == "test-component"
        assert alert.trace_id == "trace-123"

    def test_get_alerts(self):
        manager = AlertManager()
        alert = manager.create_alert(AlertLevel.WARNING, "Test", "test")
        alerts = manager.get_alerts()
        assert len(alerts) >= 1
        assert any(a.alert_id == alert.alert_id for a in alerts)

    def test_get_alerts_by_level(self):
        manager = AlertManager()
        manager.create_alert(AlertLevel.WARNING, "Warning 1", "test")
        manager.create_alert(AlertLevel.ERROR, "Error 1", "test")
        warnings = manager.get_alerts(level=AlertLevel.WARNING)
        errors = manager.get_alerts(level=AlertLevel.ERROR)
        assert len(warnings) >= 1
        assert len(errors) >= 1

    def test_get_alerts_unacknowledged(self):
        manager = AlertManager()
        alert = manager.create_alert(AlertLevel.WARNING, "Test", "test")
        unacknowledged = manager.get_alerts(acknowledged=False)
        assert len(unacknowledged) >= 1
        assert any(a.alert_id == alert.alert_id for a in unacknowledged)

    def test_acknowledge_alert(self):
        manager = AlertManager()
        alert = manager.create_alert(AlertLevel.WARNING, "Test", "test")
        result = manager.acknowledge_alert(alert.alert_id)
        assert result is True
        acknowledged = manager.get_alerts(acknowledged=True)
        assert any(a.alert_id == alert.alert_id for a in acknowledged)

    def test_acknowledge_nonexistent_alert(self):
        manager = AlertManager()
        result = manager.acknowledge_alert("nonexistent-alert")
        assert result is False

    def test_get_alert_count(self):
        manager = AlertManager()
        manager.create_alert(AlertLevel.ERROR, "Test", "test")
        count = manager.get_alert_count(AlertLevel.ERROR)
        assert count >= 1

    def test_get_summary(self):
        manager = AlertManager()
        summary = manager.get_summary()
        assert "total_alerts" in summary
        assert "critical_alerts" in summary
        assert "unacknowledged_alerts" in summary

    def test_callback_notification(self):
        manager = AlertManager()
        received_alerts = []

        def callback(alert):
            received_alerts.append(alert)

        manager.register_callback(callback)
        alert = manager.create_alert(AlertLevel.WARNING, "Test", "test")
        assert any(a.alert_id == alert.alert_id for a in received_alerts)


class TestHealthMonitor:
    def test_record_diagnosis_success(self):
        monitor = HealthMonitor()
        monitor.record_diagnosis(True)
        metrics = monitor.get_metrics()
        assert metrics["total_diagnosis_requests"] == 1
        assert metrics["successful_diagnoses"] == 1

    def test_record_diagnosis_failure(self):
        monitor = HealthMonitor()
        monitor.record_diagnosis(False)
        metrics = monitor.get_metrics()
        assert metrics["failed_diagnoses"] == 1

    def test_record_patch_success(self):
        monitor = HealthMonitor()
        monitor.record_patch(True)
        metrics = monitor.get_metrics()
        assert metrics["successful_patches"] == 1

    def test_record_patch_failure(self):
        monitor = HealthMonitor()
        monitor.record_patch(False)
        metrics = monitor.get_metrics()
        assert metrics["failed_patches"] == 1

    def test_record_approval(self):
        monitor = HealthMonitor()
        monitor.record_approval(True)
        monitor.record_approval(False)
        metrics = monitor.get_metrics()
        assert metrics["approvals_granted"] == 1
        assert metrics["approvals_rejected"] == 1

    def test_record_convergence(self):
        monitor = HealthMonitor()
        monitor.record_convergence()
        metrics = monitor.get_metrics()
        assert metrics["convergence_achieved"] == 1

    def test_get_health_status_healthy(self):
        monitor = HealthMonitor()
        status = monitor.get_health_status()
        assert status["status"] == "HEALTHY"
        assert status["diagnosis_success_rate"] == 1.0

    def test_get_health_status_degraded(self):
        monitor = HealthMonitor()
        for _ in range(4):
            monitor.record_diagnosis(True)
        for _ in range(3):
            monitor.record_diagnosis(False)
        status = monitor.get_health_status()
        assert status["status"] == "DEGRADED"

    def test_get_health_status_unhealthy(self):
        monitor = HealthMonitor()
        for _ in range(1):
            monitor.record_diagnosis(True)
        for _ in range(2):
            monitor.record_diagnosis(False)
        status = monitor.get_health_status()
        assert status["status"] == "UNHEALTHY"

    def test_get_metrics(self):
        monitor = HealthMonitor()
        metrics = monitor.get_metrics()
        assert "total_diagnosis_requests" in metrics
        assert "successful_diagnoses" in metrics
        assert "circuit_breaker_tripped" in metrics
