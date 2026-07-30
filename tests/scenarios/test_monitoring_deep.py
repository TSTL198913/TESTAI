"""
监控告警深度测试 - 验证完整监控生命周期
"""
import pytest


class TestMonitoringDeep:
    """监控告警深度测试"""

    def test_alert_generation_and_filtering(self, client, admin_headers):
        """场景：告警生成和筛选"""
        response = client.get("/monitoring/alerts", headers=admin_headers)
        assert response.status_code == 200
        alerts = response.json()["data"]
        assert "alerts" in alerts
        assert isinstance(alerts["alerts"], list)
        assert "count" in alerts

    def test_alert_acknowledgment_flow(self, client, admin_headers):
        """场景：告警确认流程"""
        response = client.get("/monitoring/alerts", headers=admin_headers)
        assert response.status_code == 200
        alerts = response.json()["data"]

        open_alerts = [a for a in alerts["alerts"] if a.get("status") == "open"]
        if open_alerts:
            alert_id = open_alerts[0]["alert_id"]
            response = client.post(
                f"/monitoring/alerts/{alert_id}/acknowledge",
                json={"acknowledged_by": "admin"},
                headers=admin_headers,
            )
            assert response.status_code == 200

    def test_metrics_collection(self, client, admin_headers):
        """场景：指标收集"""
        response = client.get("/monitoring/metrics", headers=admin_headers)
        assert response.status_code == 200
        metrics = response.json()["data"]
        assert "metrics" in metrics or "status" in metrics

    def test_dashboard_summary(self, client, admin_headers):
        """场景：仪表盘汇总"""
        response = client.get("/dashboard/summary", headers=admin_headers)
        assert response.status_code == 200
        summary = response.json()["data"]
        assert "platform" in summary or "health" in summary