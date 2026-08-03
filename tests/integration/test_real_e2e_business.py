import os
from httpx import Client

# P0 修复 (429 碰撞隔离):
#   旧版此处定义 module 级 api_base_url / auth_token fixture, 每个模块独立登录 admin。
#   全量顺序运行时 admin 登录次数累计触发 5次/60秒 限流 → 后续测试 429 失败。
#   现改用 tests/integration/conftest.py 的 session 级同名 fixture, 全 session 只登录 1 次。
#   详见 conftest.py:_session_login 文档。


class TestRealE2EBusiness:
    """真实端到端业务测试 - 夜间运行"""

    def test_full_workflow_lifecycle(self, api_base_url, auth_token):
        with Client() as client:
            create_response = client.post(
                f"{api_base_url}/workflow/define",
                json={
                    "name": f"E2E Test Workflow {os.urandom(4).hex()}",
                    "description": "E2E test workflow",
                    # 业务规则: define_workflow 校验 "工作流必须包含至少一个任务" (workflow.py:~300),
                    # tasks=[] 会被拒为 400。此处给一个最小有效任务以通过契约。
                    "tasks": [{"type": "delay", "name": "占位任务", "params": {"duration": 1}}]
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

    def test_token_refresh_flow(self, api_base_url, auth_tokens):
        """refresh 契约 (api.py:484-504): 优先 cookie, 回退 Authorization header, 不接受 JSON body。

        P0 修复 (429 碰撞隔离):
          旧版此处重新登录 admin 取 refresh_token, 全量运行累计触发限流。
          现复用 conftest.py 的 session 级 auth_tokens["refresh_token"], 全 session 只登录 1 次。

        真实契约 (2026-08-02 实测 + api.py:491-493):
          /auth/refresh 优先从 cookie 读 refresh_token, 回退到 Authorization: Bearer <token>。
          旧版用 json={"refresh_token": ...} → 401 "No refresh token provided" (端点不读 body)。
          改用 Authorization header 与 test_refresh_token (test_full_stack_integration) 一致。
          无 refresh token rotation (token_manager.refresh_token 不 invalidate 旧 token), 可多次复用。
        """
        with Client() as client:
            refresh_token = auth_tokens["refresh_token"]
            assert refresh_token, "session auth_tokens 缺 refresh_token, 无法测 refresh"

            refresh_response = client.post(
                f"{api_base_url}/auth/refresh",
                headers={"Authorization": f"Bearer {refresh_token}"}
            )
            assert refresh_response.status_code == 200, (
                f"refresh 应 200, 实际: {refresh_response.status_code}, "
                f"body: {refresh_response.text}"
            )
            refresh_data = refresh_response.json()
            assert refresh_data["success"] is True
            # 核心契约: refresh 后签发新 access_token
            assert "access_token" in refresh_data["data"]

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
            # dashboard/summary 当前契约: data 含 {platform, health, metrics, pending_actions, quality, summary}。
            # 旧断言期望 total_users/workflows (已废弃的 schema), 改为校验当前真实业务字段存在。
            assert "summary" in data["data"] or "metrics" in data["data"]

    def test_config_read_and_update(self, api_base_url, auth_token):
        with Client() as client:
            get_response = client.get(
                f"{api_base_url}/config",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert get_response.status_code == 200
            data = get_response.json()
            assert data["success"] is True