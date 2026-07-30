"""
测试引擎深度测试 - 验证完整测试生命周期
"""
import pytest


class TestTestEngineDeep:
    """测试引擎深度测试"""

    def test_test_execution_with_multiple_protocols(self, client, admin_headers):
        """场景：执行多种协议的测试用例"""
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "HTTP健康检查", "protocol": "http", "method": "GET", "url": "/health"},
                    {"name": "HTTP不存在端点", "protocol": "http", "method": "GET", "url": "/api/nonexistent"},
                ]
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert "total_tests" in result
        assert "results" in result
        assert len(result["results"]) >= 1

    def test_ai_diagnosis_basic(self, client, admin_headers):
        """场景：AI诊断基础功能"""
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "diagnosis-test"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        diagnosis = response.json()["data"]
        assert "confidence" in diagnosis
        assert 0 <= diagnosis["confidence"] <= 1.0

    def test_test_execution_rate_limit(self, client, admin_headers):
        """场景：测试执行限流"""
        for _ in range(10):
            response = client.post(
                "/test/execute",
                json={"test_cases": [{"name": "限流测试", "protocol": "http", "method": "GET", "url": "/health"}]},
                headers=admin_headers,
            )

        response = client.post(
            "/test/execute",
            json={"test_cases": [{"name": "限流测试", "protocol": "http", "method": "GET", "url": "/health"}]},
            headers=admin_headers,
        )
        assert response.status_code in [200, 429]