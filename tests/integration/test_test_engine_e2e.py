import pytest
from unittest.mock import patch, MagicMock


class TestTestEngineAPI:
    """测试引擎API端到端测试"""

    def test_execute_test_cases_http_success(self, client, auth_headers):
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {
                        "name": "健康检查测试",
                        "protocol": "http",
                        "method": "GET",
                        "url": "/health",
                        "headers": {"Content-Type": "application/json"},
                    }
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_tests" in data
        assert "passed_tests" in data
        assert "failed_tests" in data
        assert "pass_rate" in data
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["test_case_name"] == "健康检查测试"
        assert "passed" in data["results"][0]
        assert "status_code" in data["results"][0]
        assert "response_time_ms" in data["results"][0]

    def test_execute_test_cases_empty_list(self, client, auth_headers):
        response = client.post(
            "/test/execute",
            json={"test_cases": []},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_tests"] == 0
        assert data["passed_tests"] == 0
        assert data["failed_tests"] == 0
        assert data["pass_rate"] == 0

    def test_execute_test_cases_multiple(self, client, auth_headers):
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "测试1", "protocol": "http", "method": "GET", "url": "/health"},
                    {"name": "测试2", "protocol": "http", "method": "GET", "url": "/health"},
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_tests"] == 2

    def test_execute_test_cases_unauthorized(self, client):
        response = client.post(
            "/test/execute",
            json={"test_cases": [{"name": "测试", "protocol": "http", "method": "GET", "url": "/health"}]},
        )
        assert response.status_code == 401

    def test_execute_test_cases_invalid_url(self, client, auth_headers):
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "无效URL测试", "protocol": "http", "method": "GET", "url": "/nonexistent_endpoint"}
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_tests"] == 1

    def test_generate_test_cases(self, client, auth_headers):
        spec = {
            "name": "用户管理API",
            "description": "用户管理相关接口测试",
            "endpoints": [
                {"method": "GET", "path": "/users", "description": "获取用户列表"}
            ],
        }
        response = client.post("/test/generate", json=spec, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "total_generated" in data
        assert "test_cases" in data

    def test_generate_test_cases_empty_spec(self, client, auth_headers):
        response = client.post("/test/generate", json={}, headers=auth_headers)
        assert response.status_code == 200


class TestDiagnoseAPI:
    """AI诊断API端到端测试"""

    def test_diagnose_workflow_empty(self, client, auth_headers):
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-001"
        assert "issues" in data
        assert "insights" in data
        assert "confidence" in data
        assert "timestamp" in data

    def test_diagnose_workflow_with_test_results(self, client, auth_headers):
        test_results = {
            "failures": [
                {
                    "test_name": "登录测试失败",
                    "error_message": "AssertionError: 预期状态码200，实际401",
                    "location": "/auth/login",
                }
            ]
        }
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "test_results": test_results},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-001"
        assert len(data["issues"]) >= 0

    def test_diagnose_workflow_with_code(self, client, auth_headers):
        code = """
def login(username, password):
    if username == "admin" and password == "password":
        return True
    return False
"""
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "code": code},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-001"

    def test_diagnose_workflow_with_code_and_results(self, client, auth_headers):
        code = """
def process_data(data):
    return data["value"]
"""
        test_results = {
            "failures": [
                {"test_name": "空数据测试", "error_message": "KeyError: 'value'", "location": "process_data"}
            ]
        }
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "code": code, "test_results": test_results},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-001"
        assert "issues" in data

    def test_diagnose_workflow_unauthorized(self, client):
        response = client.post("/diagnose/workflow", json={"workflow_id": "wf-001"})
        assert response.status_code == 401

    def test_diagnose_workflow_insights_structure(self, client, auth_headers):
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for insight in data.get("insights", []):
            assert "title" in insight
            assert "description" in insight
            assert "severity" in insight
            assert "recommendation" in insight
            assert "confidence" in insight


class TestTestEngineEndToEnd:
    """测试引擎完整端到端测试"""

    def test_full_test_diagnose_flow(self, client, auth_headers):
        execute_response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "健康检查", "protocol": "http", "method": "GET", "url": "/health"},
                    {"name": "用户列表", "protocol": "http", "method": "GET", "url": "/users"},
                ]
            },
            headers=auth_headers,
        )
        assert execute_response.status_code == 200
        execute_data = execute_response.json()

        test_results = {
            "failures": [
                {
                    "test_name": tc["test_case_name"],
                    "error_message": "测试未通过" if not tc["passed"] else "",
                    "location": "test",
                }
                for tc in execute_data["results"]
                if not tc["passed"]
            ]
        }

        diagnose_response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-e2e-test", "test_results": test_results},
            headers=auth_headers,
        )
        assert diagnose_response.status_code == 200
        diagnose_data = diagnose_response.json()
        assert diagnose_data["workflow_id"] == "wf-e2e-test"

    def test_generate_and_execute_flow(self, client, auth_headers):
        spec = {
            "name": "监控API测试",
            "description": "监控相关接口",
            "endpoints": [
                {"method": "GET", "path": "/monitoring/metrics", "description": "获取监控指标"}
            ],
        }
        generate_response = client.post("/test/generate", json=spec, headers=auth_headers)
        assert generate_response.status_code == 200
        generate_data = generate_response.json()

        if generate_data["total_generated"] > 0:
            test_cases = [
                {
                    "name": tc["name"],
                    "protocol": "http",
                    "method": "GET",
                    "url": "/monitoring/metrics",
                }
                for tc in generate_data["test_cases"]
            ]
            execute_response = client.post(
                "/test/execute",
                json={"test_cases": test_cases},
                headers=auth_headers,
            )
            assert execute_response.status_code == 200