"""
Platform DashboardService测试 - 覆盖五种场景
目标覆盖率≥80%
"""
import pytest
from datetime import datetime, timedelta

from src.platform.dashboard import DashboardService


class TestDashboardService:
    """DashboardService测试类"""

    # === 正向场景 ===
    def test_get_quality_trend_returns_data(self):
        """正向：获取质量趋势数据"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=7)
        
        assert "days" in trend
        assert "data" in trend
        assert "trends" in trend
        
        assert trend["days"] == 7
        assert len(trend["data"]) == 7
        
        trends = trend["trends"]
        assert "pass_rate" in trends
        assert "kill_rate" in trends
        assert "automation_rate" in trends
        assert "defects_found" in trends

    def test_get_quality_trend_days_limited(self):
        """正向：限制天数返回对应数据"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=3)
        
        assert trend["days"] == 3
        assert len(trend["data"]) == 3

    def test_get_workflow_stats_returns_dict(self):
        """正向：获取工作流统计"""
        dashboard = DashboardService()
        stats = dashboard.get_workflow_stats()
        
        assert isinstance(stats, dict)
        assert "total_workflows" in stats
        assert "active_workflows" in stats
        assert "completed_workflows" in stats
        assert "failed_workflows" in stats
        assert "avg_execution_time" in stats

    def test_calculate_trend_improving(self):
        """正向：趋势计算-改善"""
        dashboard = DashboardService()
        values = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98]
        trend = dashboard._calculate_trend(values)
        
        assert trend == "improving"

    def test_calculate_trend_declining(self):
        """正向：趋势计算-下降"""
        dashboard = DashboardService()
        values = [0.98, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7]
        trend = dashboard._calculate_trend(values)
        
        assert trend == "declining"

    def test_calculate_trend_stable(self):
        """正向：趋势计算-稳定"""
        dashboard = DashboardService()
        values = [0.85, 0.86, 0.84, 0.85, 0.86, 0.84, 0.85]
        trend = dashboard._calculate_trend(values)
        
        assert trend == "stable"

    # === 负向场景 ===
    def test_calculate_trend_single_value(self):
        """负向：单值趋势返回稳定"""
        dashboard = DashboardService()
        values = [0.85]
        trend = dashboard._calculate_trend(values)
        
        assert trend == "stable"

    def test_calculate_trend_two_values_stable(self):
        """负向：两个接近的值返回稳定"""
        dashboard = DashboardService()
        values = [0.85, 0.86]
        trend = dashboard._calculate_trend(values)
        
        assert trend == "stable"

    def test_get_quality_trend_zero_days(self):
        """负向：零天返回空数据"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=0)
        
        assert trend["days"] == 0
        assert len(trend["data"]) == 0

    # === 边界场景 ===
    def test_get_quality_trend_more_than_available(self):
        """边界：请求天数超过可用数据"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=100)
        
        assert trend["days"] == 100
        assert len(trend["data"]) == 7

    def test_get_quality_trend_negative_days(self):
        """边界：负天数"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=-1)
        
        assert trend["days"] == -1
        assert len(trend["data"]) == 6

    def test_initial_data_generation(self):
        """边界：初始数据生成"""
        dashboard = DashboardService()
        
        assert len(dashboard._quality_metrics) == 7
        for metric in dashboard._quality_metrics:
            assert "date" in metric
            assert "test_count" in metric
            assert "pass_rate" in metric
            assert "kill_rate" in metric
            assert "defects_found" in metric
            assert "automation_rate" in metric

    # === 依赖场景 ===
    def test_quality_trend_order(self):
        """依赖：趋势数据按时间升序"""
        dashboard = DashboardService()
        trend = dashboard.get_quality_trend(days=7)
        
        dates = [m["date"] for m in trend["data"]]
        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i + 1]

    def test_quality_metrics_pass_rate_range(self):
        """依赖：通过率在有效范围内"""
        dashboard = DashboardService()
        for metric in dashboard._quality_metrics:
            assert 0 <= metric["pass_rate"] <= 1
            assert 0 <= metric["kill_rate"] <= 1
            assert 0 <= metric["automation_rate"] <= 1

    @pytest.mark.asyncio
    async def test_get_summary(self):
        """正向：获取仪表盘摘要"""
        from unittest.mock import patch, MagicMock
        
        with patch("src.governance.monitoring.HealthMonitor") as mock_health, \
             patch("src.governance.monitoring.AlertManager") as mock_alert, \
             patch("src.governance.approval.ApprovalManager") as mock_approval:
            
            mock_health_instance = MagicMock()
            mock_health.return_value = mock_health_instance
            mock_health_instance.get_health_status.return_value = {"status": "healthy", "diagnosis_success_rate": 0.95, "patch_success_rate": 0.9}
            mock_health_instance.get_metrics.return_value = {"total_diagnoses": 100, "successful_diagnoses": 95, "total_patch_applications": 50, "successful_patches": 45}
            
            mock_alert_instance = MagicMock()
            mock_alert.return_value = mock_alert_instance
            mock_alert_instance.get_alerts_unacknowledged.return_value = []
            
            mock_approval_instance = MagicMock()
            mock_approval.return_value = mock_approval_instance
            mock_approval_instance.list_pending.return_value = []
            
            dashboard = DashboardService()
            summary = dashboard.get_summary()
            
            assert "platform" in summary
            assert "health" in summary
            assert "metrics" in summary
            assert "pending_actions" in summary
            assert "quality" in summary
            assert "summary" in summary
            
            assert summary["platform"]["name"] == "TestAI Platform"
            assert summary["platform"]["version"] == "1.0.0"
            assert summary["platform"]["status"] == "operational"
            
            assert "today_tests" in summary["summary"]
            assert "today_pass_rate" in summary["summary"]
            assert "today_kill_rate" in summary["summary"]

    @pytest.mark.asyncio
    async def test_get_system_health(self):
        """正向：获取系统健康状态"""
        dashboard = DashboardService()
        health = dashboard.get_system_health()
        
        assert "status" in health
        assert "metrics" in health
        assert "alerts" in health
        assert "last_updated" in health
        
        assert "total" in health["alerts"]
        assert "critical" in health["alerts"]
        assert "error" in health["alerts"]
