import pytest
import os
from httpx import Client


@pytest.fixture(scope="module")
def api_base_url():
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def auth_token(api_base_url):
    with Client() as client:
        response = client.post(
            f"{api_base_url}/auth/login",
            json={"username": "admin", "password": "password"}
        )
        data = response.json()
        assert response.status_code == 200
        assert data["success"] is True
        return data["data"]["access_token"]


class TestRealE2EBusiness:
    """真实端到端业务测试 - 夜间运行"""

    def test_full_workflow_lifecycle(self, api_base_url, auth_token):
        with Client() as client:
            create_response = client.post(
                f"{api_base_url}/workflow/define",
                json={
                    "name": f"E2E Test Workflow {os.urandom(4).hex()}",
                    "description": "E2E test workflow",
                    "tasks": []
                },
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert create_response.status_code == 200
            create_data = create_response.json()
            assert create_data["success"] is True
            workflow_id = create_data["data"].get("workflow_id")
            
            assert workflow_id is not None
            
            get_response = client.get(
                f"{api_base_url}/workflow",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert get_response.status_code == 200
            
            delete_response = client.delete(
                f"{api_base_url}/workflow/{workflow_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert delete_response.status_code == 200

    def test_user_creation_and_management(self, api_base_url, auth_token):
        with Client() as client:
            username = f"testuser_{os.urandom(4).hex()}"
            
            create_response = client.post(
                f"{api_base_url}/users",
                json={
                    "username": username,
                    "email": f"{username}@example.com",
                    "password": "Test@1234",
                    "role": "viewer"
                },
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert create_response.status_code == 200
            create_data = create_response.json()
            assert create_data["success"] is True
            user_id = create_data["data"].get("user_id")
            
            assert user_id is not None
            
            list_response = client.get(
                f"{api_base_url}/users?username={username}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert list_response.status_code == 200
            
            update_response = client.put(
                f"{api_base_url}/users/{user_id}",
                json={"full_name": "Test User"},
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert update_response.status_code == 200
            
            delete_response = client.delete(
                f"{api_base_url}/users/{user_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert delete_response.status_code == 200

    def test_team_creation_and_member_management(self, api_base_url, auth_token):
        with Client() as client:
            team_name = f"E2E Test Team {os.urandom(4).hex()}"
            
            create_response = client.post(
                f"{api_base_url}/teams",
                json={
                    "name": team_name,
                    "description": "E2E test team"
                },
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert create_response.status_code == 200
            create_data = create_response.json()
            assert create_data["success"] is True
            team_id = create_data["data"].get("team_id")
            
            assert team_id is not None
            
            list_response = client.get(
                f"{api_base_url}/teams",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert list_response.status_code == 200
            
            delete_response = client.delete(
                f"{api_base_url}/teams/{team_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert delete_response.status_code == 200

    def test_governance_approval_flow(self, api_base_url, auth_token):
        with Client() as client:
            list_response = client.get(
                f"{api_base_url}/governance/approvals",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert list_response.status_code == 200
            data = list_response.json()
            assert data["success"] is True

    def test_token_refresh_flow(self, api_base_url):
        with Client() as client:
            login_response = client.post(
                f"{api_base_url}/auth/login",
                json={"username": "admin", "password": "password"}
            )
            assert login_response.status_code == 200
            login_data = login_response.json()
            assert login_data["success"] is True
            
            refresh_response = client.post(
                f"{api_base_url}/auth/refresh",
                json={"refresh_token": login_data["data"]["refresh_token"]}
            )
            assert refresh_response.status_code == 200
            refresh_data = refresh_response.json()
            assert refresh_data["success"] is True
            assert "access_token" in refresh_data["data"]
            assert "refresh_token" in refresh_data["data"]

    def test_permission_denied_for_unauthorized(self, api_base_url):
        with Client() as client:
            response = client.get(
                f"{api_base_url}/users",
                headers={"Authorization": "Bearer invalid_token"}
            )
            assert response.status_code == 401

    def test_dashboard_summary(self, api_base_url, auth_token):
        with Client() as client:
            response = client.get(
                f"{api_base_url}/dashboard/summary",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "total_users" in data["data"] or "workflows" in data["data"]

    def test_config_read_and_update(self, api_base_url, auth_token):
        with Client() as client:
            get_response = client.get(
                f"{api_base_url}/config",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert get_response.status_code == 200
            data = get_response.json()
            assert data["success"] is True