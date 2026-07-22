import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class AlertLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertType(str, Enum):
    TEST_FAILURE = "test_failure"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SYSTEM_ERROR = "system_error"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    SECURITY_BREACH = "security_breach"
    INTEGRATION_FAILURE = "integration_failure"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class Alert:
    alert_id: str
    level: AlertLevel
    alert_type: AlertType
    title: str
    message: str
    source: str = ""
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    status: AlertStatus = AlertStatus.OPEN
    acknowledged_by: str = ""
    acknowledged_at: Optional[datetime] = None
    resolved_by: str = ""
    resolved_at: Optional[datetime] = None


@dataclass
class AlertRule:
    rule_id: str
    name: str
    alert_type: AlertType
    level: AlertLevel
    condition: str
    threshold: float
    window_seconds: int = 300
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)


class AlertManager:
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or os.environ.get(
            "ALERT_STORAGE_PATH", "data/alerts.json"
        )
        self.alerts: List[Alert] = []
        self.rules: Dict[str, AlertRule] = {}
        self._load_alerts()
        self._initialize_default_rules()

    def _load_alerts(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for alert_data in data.get("alerts", []):
                        self.alerts.append(
                            Alert(
                                alert_id=alert_data["alert_id"],
                                level=AlertLevel(alert_data["level"]),
                                alert_type=AlertType(alert_data["alert_type"]),
                                title=alert_data["title"],
                                message=alert_data["message"],
                                source=alert_data.get("source", ""),
                                details=alert_data.get("details", {}),
                                timestamp=datetime.fromisoformat(alert_data["timestamp"]),
                                status=AlertStatus(alert_data.get("status", "open")),
                                acknowledged_by=alert_data.get("acknowledged_by", ""),
                                acknowledged_at=datetime.fromisoformat(alert_data["acknowledged_at"])
                                if alert_data.get("acknowledged_at")
                                else None,
                                resolved_by=alert_data.get("resolved_by", ""),
                                resolved_at=datetime.fromisoformat(alert_data["resolved_at"])
                                if alert_data.get("resolved_at")
                                else None,
                            )
                        )
            except Exception:
                self.alerts = []

    def _save_alerts(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "alerts": [],
            "rules": [],
        }

        for alert in self.alerts[-5000:]:
            data["alerts"].append(
                {
                    "alert_id": alert.alert_id,
                    "level": alert.level.value,
                    "alert_type": alert.alert_type.value,
                    "title": alert.title,
                    "message": alert.message,
                    "source": alert.source,
                    "details": alert.details,
                    "timestamp": alert.timestamp.isoformat(),
                    "status": alert.status.value,
                    "acknowledged_by": alert.acknowledged_by,
                    "acknowledged_at": alert.acknowledged_at.isoformat()
                    if alert.acknowledged_at
                    else None,
                    "resolved_by": alert.resolved_by,
                    "resolved_at": alert.resolved_at.isoformat()
                    if alert.resolved_at
                    else None,
                }
            )

        for rule in self.rules.values():
            data["rules"].append(
                {
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "alert_type": rule.alert_type.value,
                    "level": rule.level.value,
                    "condition": rule.condition,
                    "threshold": rule.threshold,
                    "window_seconds": rule.window_seconds,
                    "enabled": rule.enabled,
                    "created_at": rule.created_at.isoformat(),
                }
            )

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _initialize_default_rules(self):
        default_rules = [
            AlertRule(
                rule_id="rule_test_failure",
                name="测试失败率超过阈值",
                alert_type=AlertType.TEST_FAILURE,
                level=AlertLevel.WARNING,
                condition="failed_ratio > threshold",
                threshold=0.1,
                window_seconds=300,
            ),
            AlertRule(
                rule_id="rule_performance",
                name="响应时间超过阈值",
                alert_type=AlertType.PERFORMANCE_DEGRADATION,
                level=AlertLevel.WARNING,
                condition="avg_response_time > threshold",
                threshold=2000,
                window_seconds=300,
            ),
            AlertRule(
                rule_id="rule_performance_critical",
                name="响应时间严重超时",
                alert_type=AlertType.PERFORMANCE_DEGRADATION,
                level=AlertLevel.CRITICAL,
                condition="avg_response_time > threshold",
                threshold=5000,
                window_seconds=300,
            ),
            AlertRule(
                rule_id="rule_kill_rate",
                name="变异测试Kill Rate不足",
                alert_type=AlertType.TEST_FAILURE,
                level=AlertLevel.WARNING,
                condition="kill_rate < threshold",
                threshold=80,
                window_seconds=0,
            ),
            AlertRule(
                rule_id="rule_coverage",
                name="测试覆盖率不足",
                alert_type=AlertType.TEST_FAILURE,
                level=AlertLevel.WARNING,
                condition="coverage < threshold",
                threshold=80,
                window_seconds=0,
            ),
        ]

        for rule in default_rules:
            if rule.rule_id not in self.rules:
                self.rules[rule.rule_id] = rule

    def create_alert(
        self,
        level: AlertLevel,
        alert_type: AlertType,
        title: str,
        message: str,
        source: str = "",
        details: Optional[Dict] = None,
    ) -> Alert:
        alert_id = f"alert_{len(self.alerts) + 1:06d}"
        alert = Alert(
            alert_id=alert_id,
            level=level,
            alert_type=alert_type,
            title=title,
            message=message,
            source=source,
            details=details or {},
            timestamp=datetime.now(),
            status=AlertStatus.OPEN,
        )
        self.alerts.append(alert)
        self._save_alerts()
        return alert

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                return alert
        return None

    def acknowledge_alert(self, alert_id: str, user_id: str) -> Optional[Alert]:
        alert = self.get_alert(alert_id)
        if alert:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_by = user_id
            alert.acknowledged_at = datetime.now()
            self._save_alerts()
        return alert

    def resolve_alert(self, alert_id: str, user_id: str) -> Optional[Alert]:
        alert = self.get_alert(alert_id)
        if alert:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_by = user_id
            alert.resolved_at = datetime.now()
            self._save_alerts()
        return alert

    def list_alerts(
        self,
        level: Optional[AlertLevel] = None,
        alert_type: Optional[AlertType] = None,
        status: Optional[AlertStatus] = None,
        since: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        filtered = []
        for alert in self.alerts:
            if level and alert.level != level:
                continue
            if alert_type and alert.alert_type != alert_type:
                continue
            if status and alert.status != status:
                continue
            if since and alert.timestamp < since:
                continue
            filtered.append(alert)

        filtered.sort(key=lambda x: x.timestamp, reverse=True)

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = filtered[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "alerts": paginated,
        }

    def evaluate_rules(self, metrics: Dict[str, float]) -> List[Alert]:
        triggered_alerts = []

        for rule in self.rules.values():
            if not rule.enabled:
                continue

            if rule.rule_id == "rule_test_failure":
                failed_ratio = metrics.get("failed_ratio", 0)
                if failed_ratio > rule.threshold:
                    triggered_alerts.append(
                        self.create_alert(
                            level=rule.level,
                            alert_type=rule.alert_type,
                            title=f"{rule.name}: {failed_ratio:.2%}",
                            message=f"测试失败率 {failed_ratio:.2%} 超过阈值 {rule.threshold:.0%}",
                            source="test_runner",
                            details={"failed_ratio": failed_ratio, "threshold": rule.threshold},
                        )
                    )

            elif rule.rule_id == "rule_performance":
                avg_response_time = metrics.get("avg_response_time_ms", 0)
                if avg_response_time > rule.threshold:
                    triggered_alerts.append(
                        self.create_alert(
                            level=rule.level,
                            alert_type=rule.alert_type,
                            title=f"{rule.name}: {avg_response_time}ms",
                            message=f"平均响应时间 {avg_response_time}ms 超过阈值 {rule.threshold}ms",
                            source="api_monitor",
                            details={"response_time": avg_response_time, "threshold": rule.threshold},
                        )
                    )

            elif rule.rule_id == "rule_performance_critical":
                avg_response_time = metrics.get("avg_response_time_ms", 0)
                if avg_response_time > rule.threshold:
                    triggered_alerts.append(
                        self.create_alert(
                            level=rule.level,
                            alert_type=rule.alert_type,
                            title=f"{rule.name}: {avg_response_time}ms",
                            message=f"响应时间严重超时 {avg_response_time}ms，超过阈值 {rule.threshold}ms",
                            source="api_monitor",
                            details={"response_time": avg_response_time, "threshold": rule.threshold},
                        )
                    )

            elif rule.rule_id == "rule_kill_rate":
                kill_rate = metrics.get("kill_rate", 0)
                if kill_rate < rule.threshold:
                    triggered_alerts.append(
                        self.create_alert(
                            level=rule.level,
                            alert_type=rule.alert_type,
                            title=f"{rule.name}: {kill_rate}%",
                            message=f"变异测试Kill Rate {kill_rate}% 低于阈值 {rule.threshold}%",
                            source="mutation_test",
                            details={"kill_rate": kill_rate, "threshold": rule.threshold},
                        )
                    )

            elif rule.rule_id == "rule_coverage":
                coverage = metrics.get("coverage", 0)
                if coverage < rule.threshold:
                    triggered_alerts.append(
                        self.create_alert(
                            level=rule.level,
                            alert_type=rule.alert_type,
                            title=f"{rule.name}: {coverage}%",
                            message=f"测试覆盖率 {coverage}% 低于阈值 {rule.threshold}%",
                            source="coverage_report",
                            details={"coverage": coverage, "threshold": rule.threshold},
                        )
                    )

        return triggered_alerts

    def get_alert_counts(self) -> Dict[str, int]:
        counts = {"total": len(self.alerts)}
        for level in AlertLevel:
            counts[f"level_{level.value}"] = sum(1 for a in self.alerts if a.level == level)
        for status in AlertStatus:
            counts[f"status_{status.value}"] = sum(1 for a in self.alerts if a.status == status)
        for alert_type in AlertType:
            counts[f"type_{alert_type.value}"] = sum(
                1 for a in self.alerts if a.alert_type == alert_type
            )

        last_hour = datetime.now() - timedelta(hours=1)
        counts["last_hour"] = sum(1 for a in self.alerts if a.timestamp >= last_hour)

        return counts

    def add_rule(self, rule: AlertRule):
        self.rules[rule.rule_id] = rule
        self._save_alerts()

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self.rules:
            del self.rules[rule_id]
            self._save_alerts()
            return True
        return False

    def list_rules(self) -> List[AlertRule]:
        return sorted(self.rules.values(), key=lambda r: r.created_at)