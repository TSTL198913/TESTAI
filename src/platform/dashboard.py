from datetime import datetime, timedelta
from typing import Dict, Any, List


class DashboardService:
    def __init__(self):
        self._quality_metrics = []
        self._generate_initial_data()

    def _generate_initial_data(self):
        now = datetime.now()
        for i in range(7):
            date = now - timedelta(days=i)
            self._quality_metrics.append({
                "date": date.date().isoformat(),
                "test_count": 100 + i * 10,
                "pass_rate": min(0.95, 0.75 + i * 0.03),
                "kill_rate": min(0.85, 0.60 + i * 0.04),
                "defects_found": 15 - i * 2,
                "automation_rate": min(0.80, 0.50 + i * 0.05),
            })

    def get_summary(self) -> Dict[str, Any]:
        from src.governance.monitoring import HealthMonitor, AlertManager
        from src.governance.approval import ApprovalManager

        health_monitor = HealthMonitor()
        alert_manager = AlertManager()
        approval_manager = ApprovalManager()

        health_status = health_monitor.get_health_status()
        metrics = health_monitor.get_metrics()

        pending_approvals = approval_manager.list_pending()
        unacknowledged_alerts = alert_manager.get_alerts_unacknowledged()

        recent_metrics = self._quality_metrics[-1] if self._quality_metrics else {}

        return {
            "platform": {
                "name": "TestAI Platform",
                "version": "1.0.0",
                "status": "operational",
            },
            "health": {
                "status": health_status.get("status", "UNKNOWN"),
                "diagnosis_success_rate": health_status.get("diagnosis_success_rate", 0),
                "patch_success_rate": health_status.get("patch_success_rate", 0),
            },
            "metrics": {
                "total_diagnoses": metrics.get("total_diagnoses", 0),
                "successful_diagnoses": metrics.get("successful_diagnoses", 0),
                "total_patch_applications": metrics.get("total_patch_applications", 0),
                "successful_patches": metrics.get("successful_patches", 0),
            },
            "pending_actions": {
                "approvals": len(pending_approvals),
                "unacknowledged_alerts": len(unacknowledged_alerts),
            },
            "quality": {
                "test_count": recent_metrics.get("test_count", 0),
                "pass_rate": recent_metrics.get("pass_rate", 0),
                "kill_rate": recent_metrics.get("kill_rate", 0),
                "defects_found": recent_metrics.get("defects_found", 0),
                "automation_rate": recent_metrics.get("automation_rate", 0),
            },
            "summary": {
                "today_tests": recent_metrics.get("test_count", 0),
                "today_pass_rate": f"{recent_metrics.get('pass_rate', 0) * 100:.1f}%",
                "today_kill_rate": f"{recent_metrics.get('kill_rate', 0) * 100:.1f}%",
                "total_pending_approvals": len(pending_approvals),
                "unacknowledged_alerts": len(unacknowledged_alerts),
            },
        }

    def get_quality_trend(self, days: int = 7) -> Dict[str, Any]:
        recent = self._quality_metrics[:days]
        recent.reverse()

        return {
            "days": days,
            "data": recent,
            "trends": {
                "pass_rate": self._calculate_trend([m["pass_rate"] for m in recent]),
                "kill_rate": self._calculate_trend([m["kill_rate"] for m in recent]),
                "automation_rate": self._calculate_trend([m["automation_rate"] for m in recent]),
                "defects_found": self._calculate_trend([m["defects_found"] for m in recent]),
            },
        }

    def _calculate_trend(self, values: List[float]) -> str:
        if len(values) < 2:
            return "stable"

        recent = values[-3:]
        older = values[:3] if len(values) >= 6 else values[:-3]

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else recent_avg

        if recent_avg > older_avg * 1.05:
            return "improving"
        elif recent_avg < older_avg * 0.95:
            return "declining"
        else:
            return "stable"

    def get_workflow_stats(self) -> Dict[str, Any]:
        return {
            "total_workflows": 0,
            "active_workflows": 0,
            "completed_workflows": 0,
            "failed_workflows": 0,
            "avg_execution_time": "0m",
        }

    def get_system_health(self) -> Dict[str, Any]:
        from src.governance.monitoring import HealthMonitor, AlertManager

        health_monitor = HealthMonitor()
        alert_manager = AlertManager()

        status = health_monitor.get_health_status()
        metrics = health_monitor.get_metrics()
        alerts = alert_manager.get_alerts()

        critical_alerts = [a for a in alerts if a.level == "CRITICAL"]
        error_alerts = [a for a in alerts if a.level == "ERROR"]

        return {
            "status": status.get("status", "UNKNOWN"),
            "metrics": metrics,
            "alerts": {
                "total": len(alerts),
                "critical": len(critical_alerts),
                "error": len(error_alerts),
            },
            "last_updated": datetime.now().isoformat(),
        }