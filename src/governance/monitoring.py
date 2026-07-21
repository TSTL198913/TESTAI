import json
import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from src.governance.config import GovernanceConfig


class AlertLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertRecord:
    def __init__(
        self,
        alert_id: str,
        level: str,
        message: str,
        component: str,
        trace_id: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        self.alert_id = alert_id
        self.level = level
        self.message = message
        self.component = component
        self.trace_id = trace_id
        self.details = details or {}
        self.created_at = datetime.now()
        self.acknowledged = False

    def to_dict(self) -> Dict:
        return {
            "alert_id": self.alert_id,
            "level": self.level,
            "message": self.message,
            "component": self.component,
            "trace_id": self.trace_id,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
        }


class StructuredLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self.logger = logging.getLogger("GovernanceMonitor")
        self.logger.setLevel(getattr(logging, GovernanceConfig.LOG_LEVEL))
        self._initialized = True

    def log(self, level: str, message: str, **kwargs):
        log_record = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        log_line = json.dumps(log_record, ensure_ascii=False)

        if level == "DEBUG":
            self.logger.debug(log_line)
        elif level == "INFO":
            self.logger.info(log_line)
        elif level == "WARNING":
            self.logger.warning(log_line)
        elif level == "ERROR":
            self.logger.error(log_line)
        elif level == "CRITICAL":
            self.logger.critical(log_line)

        return log_record


class AlertManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._alerts: List[AlertRecord] = []
        self._alert_callbacks: List[Callable] = []
        self._logger = StructuredLogger()
        self._initialized = True

    def register_callback(self, callback: Callable):
        with self._lock:
            self._alert_callbacks.append(callback)

    def _notify_callbacks(self, alert: AlertRecord):
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception:
                pass

    def create_alert(
        self,
        level: str,
        message: str,
        component: str,
        trace_id: Optional[str] = None,
        details: Optional[Dict] = None,
    ) -> AlertRecord:
        alert_id = f"alert-{int(time.time())}-{len(self._alerts) + 1}"
        alert = AlertRecord(
            alert_id=alert_id,
            level=level,
            message=message,
            component=component,
            trace_id=trace_id,
            details=details,
        )

        with self._lock:
            self._alerts.append(alert)

        self._logger.log(
            level, message, component=component, trace_id=trace_id, details=details
        )
        self._notify_callbacks(alert)

        if GovernanceConfig.is_alert_configured():
            self._send_webhook(alert)

        return alert

    def _send_webhook(self, alert: AlertRecord):
        import requests

        try:
            requests.post(
                GovernanceConfig.ALERT_WEBHOOK_URL, json=alert.to_dict(), timeout=5
            )
        except Exception:
            pass

    def acknowledge_alert(self, alert_id: str) -> bool:
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    self._logger.log("INFO", f"Alert acknowledged: {alert_id}")
                    return True
        return False

    def get_alerts(
        self, level: Optional[str] = None, acknowledged: Optional[bool] = None
    ) -> List[AlertRecord]:
        with self._lock:
            alerts = self._alerts.copy()
            if level:
                alerts = [a for a in alerts if a.level == level]
            if acknowledged is not None:
                alerts = [a for a in alerts if a.acknowledged == acknowledged]
            return sorted(alerts, key=lambda x: x.created_at, reverse=True)

    def get_alert_count(self, level: Optional[str] = None) -> int:
        alerts = self.get_alerts(level=level)
        return len(alerts)

    def get_summary(self) -> Dict:
        return {
            "total_alerts": len(self._alerts),
            "critical_alerts": self.get_alert_count(AlertLevel.CRITICAL),
            "error_alerts": self.get_alert_count(AlertLevel.ERROR),
            "warning_alerts": self.get_alert_count(AlertLevel.WARNING),
            "info_alerts": self.get_alert_count(AlertLevel.INFO),
            "unacknowledged_alerts": len(self.get_alerts(acknowledged=False)),
        }


class HealthMonitor:
    def __init__(self):
        self._metrics = {
            "total_diagnosis_requests": 0,
            "successful_diagnoses": 0,
            "failed_diagnoses": 0,
            "total_patch_applications": 0,
            "successful_patches": 0,
            "failed_patches": 0,
            "approval_requests": 0,
            "approvals_granted": 0,
            "approvals_rejected": 0,
            "circuit_breaker_tripped": 0,
            "convergence_achieved": 0,
        }
        self._lock = threading.Lock()
        self._alert_manager = AlertManager()
        self._logger = StructuredLogger()

    def increment_metric(self, metric_name: str):
        with self._lock:
            if metric_name in self._metrics:
                self._metrics[metric_name] += 1

    def record_diagnosis(self, success: bool):
        self.increment_metric("total_diagnosis_requests")
        if success:
            self.increment_metric("successful_diagnoses")
        else:
            self.increment_metric("failed_diagnoses")
            if self._metrics["failed_diagnoses"] % 5 == 0:
                self._alert_manager.create_alert(
                    AlertLevel.WARNING,
                    f"High failure rate detected: {self._metrics['failed_diagnoses']} failed diagnoses",
                    "diagnosis",
                )

    def record_patch(self, success: bool):
        self.increment_metric("total_patch_applications")
        if success:
            self.increment_metric("successful_patches")
        else:
            self.increment_metric("failed_patches")
            self._alert_manager.create_alert(
                AlertLevel.ERROR, "Patch application failed", "executor"
            )

    def record_approval(self, approved: bool):
        self.increment_metric("approval_requests")
        if approved:
            self.increment_metric("approvals_granted")
        else:
            self.increment_metric("approvals_rejected")

    def record_circuit_breaker_tripped(self):
        self.increment_metric("circuit_breaker_tripped")
        self._alert_manager.create_alert(
            AlertLevel.CRITICAL,
            "Circuit breaker tripped - governance service unavailable",
            "resilience",
        )

    def record_convergence(self):
        self.increment_metric("convergence_achieved")
        self._logger.log("INFO", "Convergence achieved", component="convergence")

    def get_metrics(self) -> Dict:
        with self._lock:
            return self._metrics.copy()

    def get_health_status(self) -> Dict:
        metrics = self.get_metrics()
        total_diagnoses = metrics["total_diagnosis_requests"]
        diagnosis_success_rate = (
            metrics["successful_diagnoses"] / total_diagnoses
            if total_diagnoses > 0
            else 1.0
        )
        total_patches = metrics["total_patch_applications"]
        patch_success_rate = (
            metrics["successful_patches"] / total_patches if total_patches > 0 else 1.0
        )

        status = "HEALTHY"
        if diagnosis_success_rate < 0.7 or patch_success_rate < 0.7:
            status = "DEGRADED"
        if diagnosis_success_rate < 0.5 or patch_success_rate < 0.5:
            status = "UNHEALTHY"

        return {
            "status": status,
            "diagnosis_success_rate": round(diagnosis_success_rate, 2),
            "patch_success_rate": round(patch_success_rate, 2),
            "metrics": metrics,
            "alerts": self._alert_manager.get_summary(),
        }
