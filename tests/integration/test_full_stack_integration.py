import pytest
import requests
import json
import os
import uuid

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000")
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


class TestFullStackIntegration:
    """全栈前后端集成测试 - 验证前后端交互正确性"""

    @pytest.fixture(scope="class")
    def auth_tokens(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "password"}
        )
        assert response.status_code == 200
        data = response.json()
        return {
            "access_token": data["data"]["access_token"],
            "refresh_token": data["data"]["refresh_token"],
            "auth_headers": {"Authorization": f"Bearer {data['data']['access_token']}"}
        }

    def test_health_check(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert data["data"]["status"] == "healthy"
        assert "platform" in data["data"]
        assert data["data"]["platform"] == "TestAI"

    def test_login_api(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "password"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert "user" in data["data"]
        assert data["data"]["user"]["username"] == "admin"
        assert data["data"]["user"]["role"] == "admin"

    def test_login_invalid_credentials(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 401

    def test_refresh_token(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/auth/refresh",
            headers={"Authorization": f"Bearer {auth_tokens['refresh_token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_get_current_user(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/auth/me",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["username"] == "admin"
        assert data["data"]["role"] == "admin"
        assert "permissions" in data["data"]
        assert isinstance(data["data"]["permissions"], list)

    def test_workflow_crud_flow(self, auth_tokens):
        workflow_name = f"集成测试工作流_{str(uuid.uuid4())[:8]}"
        
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={"name": workflow_name, "description": "集成测试"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "workflow_id" in data["data"]
        workflow_id = data["data"]["workflow_id"]

        response = requests.get(f"{API_BASE}/workflow", headers=auth_tokens["auth_headers"])
        assert response.status_code == 200

        response = requests.post(
            f"{API_BASE}/workflow/{workflow_id}/execute",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        exec_data = response.json()
        
        if exec_data.get("success"):
            instance_id = exec_data["data"].get("instance_id", workflow_id)
            response = requests.get(
                f"{API_BASE}/workflow/{instance_id}/status",
                headers=auth_tokens["auth_headers"]
            )
            assert response.status_code in [200, 404]
        else:
            assert "message" in exec_data

    def test_governance_flow(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={
                "component_name": "test_component",
                "step_id": "test_step",
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/governance/approvals",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "approvals" in data["data"]

    def test_monitoring_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/monitoring/alerts",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/monitoring/metrics",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_config_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/config",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_dashboard_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/dashboard/summary",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/dashboard/quality-trend",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_user_management_api(self, auth_tokens):
        new_user = {
            "username": f"testuser_{str(uuid.uuid4())[:8]}",
            "email": f"test_{str(uuid.uuid4())[:8]}@testai.com",
            "role": "viewer"
        }
        
        response = requests.post(
            f"{API_BASE}/users",
            json=new_user,
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "user_id" in data["data"]
        user_id = data["data"]["user_id"]

        response = requests.get(
            f"{API_BASE}/users/{user_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["user_id"] == user_id

        response = requests.put(
            f"{API_BASE}/users/{user_id}",
            json={"role": "tester"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.delete(
            f"{API_BASE}/users/{user_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_team_management_api(self, auth_tokens):
        team_name = f"测试团队_{str(uuid.uuid4())[:8]}"
        
        response = requests.post(
            f"{API_BASE}/teams",
            json={"name": team_name, "description": "测试团队"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "team_id" in data["data"]
        team_id = data["data"]["team_id"]

        response = requests.get(
            f"{API_BASE}/teams/{team_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.delete(
            f"{API_BASE}/teams/{team_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_test_execution_api(self, auth_tokens):
        test_cases = [{
            "name": "测试用例1",
            "protocol": "http",
            "method": "GET",
            "url": "https://api.example.com/test",
            "headers": {"Content-Type": "application/json"},
        }]
        
        response = requests.post(
            f"{API_BASE}/test/execute",
            json={"test_cases": test_cases},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_diagnose_api(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/diagnose/workflow",
            json={"workflow_id": "test_workflow"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_rate_limiting(self):
        for _ in range(10):
            response = requests.post(
                f"{API_BASE}/auth/login",
                json={"username": "admin", "password": "wrong"}
            )
        
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers

    def test_unauthorized_access(self):
        response = requests.get(f"{API_BASE}/workflow")
        assert response.status_code == 401

        response = requests.get(f"{API_BASE}/governance/approvals")
        assert response.status_code == 401

    def test_permission_denied(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "viewer", "password": "password"}
        )
        assert response.status_code == 200
        viewer_token = response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {viewer_token}"}

        response = requests.post(
            f"{API_BASE}/governance/approvals/test/approve",
            params={"approver": "viewer"},
            headers=headers
        )
        assert response.status_code == 403

    def test_cors_headers(self):
        response = requests.get(f"{API_BASE}/health", headers={"Origin": "http://localhost:3001"})
        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers_lower
        assert "access-control-allow-credentials" in headers_lower

    def test_api_response_format(self, auth_tokens):
        endpoints = [
            f"{API_BASE}/workflow",
            f"{API_BASE}/monitoring/alerts",
            f"{API_BASE}/dashboard/summary",
        ]
        
        for endpoint in endpoints:
            response = requests.get(endpoint, headers=auth_tokens["auth_headers"])
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)

    def test_full_workflow_to_governance_flow(self, auth_tokens):
        workflow_name = f"全流程测试_{str(uuid.uuid4())[:8]}"
        
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={"name": workflow_name, "description": "全流程测试"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        workflow_id = response.json()["data"]["workflow_id"]

        response = requests.post(
            f"{API_BASE}/workflow/{workflow_id}/execute",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        exec_data = response.json()
        
        if exec_data.get("success"):
            instance_id = exec_data["data"].get("instance_id", workflow_id)
            response = requests.get(
                f"{API_BASE}/workflow/{instance_id}/status",
                headers=auth_tokens["auth_headers"]
            )
            assert response.status_code in [200, 404]

        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={"component_name": workflow_name},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/governance/approvals",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_health_check_endpoint_structure(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert "platform" in data["data"]
        assert "version" in data["data"]
        assert "governance_status" in data["data"]

    def test_version_endpoint(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "version" in data["data"]

    def test_user_list_pagination(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/users",
            params={"page": 1, "limit": 5},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "users" in data["data"]
        assert isinstance(data["data"]["users"], list)

    def test_workflow_list_with_filter(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/workflow",
            params={"name": "Test"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_governance_execute_with_params(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={
                "component_name": "test_component",
                "step_id": "test_step",
                "force": "true"
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_monitoring_alerts_with_filter(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/monitoring/alerts",
            params={"level": "ERROR"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_dashboard_quality_trend(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/dashboard/quality-trend",
            params={"days": 7},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_config_section_access(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/config",
            params={"section": "platform"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_create_workflow_with_tasks(self, auth_tokens):
        workflow_name = f"带任务工作流_{str(uuid.uuid4())[:8]}"
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={
                "name": workflow_name,
                "description": "带任务的工作流",
                "tasks": [
                    {"type": "monitoring", "name": "检查状态", "params": {"action": "get_status"}}
                ]
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "workflow_id" in data["data"]

    def test_empty_request_body(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 422

    def test_invalid_json_format(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/auth/login",
            data="not valid json",
            headers={"Content-Type": "application/json", **auth_tokens["auth_headers"]}
        )
        assert response.status_code == 422

    def test_rate_limit_response_headers(self):
        for _ in range(5):
            requests.post(
                f"{API_BASE}/auth/login",
                json={"username": "admin", "password": "wrong"}
            )
        
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "wrong"}
        )
        if response.status_code == 429:
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers

    def test_cors_preflight_request(self):
        response = requests.options(
            f"{API_BASE}/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers_lower
        assert "access-control-allow-methods" in headers_lower
        assert "access-control-allow-headers" in headers_lower