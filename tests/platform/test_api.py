import pytest
from unittest.mock import patch, MagicMock

from src.platform.api import app


class TestAuthAPI:
    """认证API测试"""

    @pytest.mark.parametrize("username,password,expected_status", [
        ("admin", "password", 200),
        ("tester", "password", 200),
        ("viewer", "password", 200),
        ("admin", "wrong_password", 401),
        ("nonexistent", "password", 401),
        ("", "password", 401),
        ("admin", "", 401),
        ("", "", 401),
    ])
    def test_login_various_credentials(self, client, username, password, expected_status):
        response = client.post("/auth/login", json={"username": username, "password": password})
        assert response.status_code == expected_status
        if expected_status == 200:
            data = response.json()
            assert data["success"] is True
            assert "access_token" in data["data"]
            assert "refresh_token" in data["data"]
            assert "user" in data["data"]
            assert data["data"]["user"]["username"] == username

    def test_login_success(self, client):
        response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert "user" in data["data"]
        assert isinstance(data["data"]["access_token"], str)
        assert len(data["data"]["access_token"]) > 100
        assert isinstance(data["data"]["refresh_token"], str)
        assert len(data["data"]["refresh_token"]) > 100

    def test_login_empty_payload(self, client):
        response = client.post("/auth/login", json={})
        assert response.status_code == 422

    def test_login_missing_username(self, client):
        response = client.post("/auth/login", json={"password": "password"})
        assert response.status_code == 422

    def test_login_missing_password(self, client):
        response = client.post("/auth/login", json={"username": "admin"})
        assert response.status_code == 422

    def test_login_special_characters(self, client):
        response = client.post("/auth/login", json={"username": "admin' OR '1'='1", "password": "password"})
        assert response.status_code == 401

    def test_refresh_token(self, client):
        login_response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        refresh_token = login_response.json()["data"]["refresh_token"]
        headers = {"Authorization": f"Bearer {refresh_token}"}
        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert isinstance(data["data"]["access_token"], str)
        assert len(data["data"]["access_token"]) > 100

    @pytest.mark.parametrize("token,expected_status", [
        ("invalid_token", 401),
        ("", 401),
        ("Bearer ", 401),
        ("abc.xyz.123", 401),
    ])
    def test_refresh_token_invalid(self, client, token, expected_status):
        headers = {"Authorization": f"Bearer {token}"} if token else {"Authorization": ""}
        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == expected_status

    def test_refresh_with_access_token(self, client):
        """P0-6 修复:用 access_token 调用 refresh 应返回 401。

        注意:P0-6 后 refresh 端点优先读 cookie 中的 refresh_token,
        所以测试必须清除 cookie,确保只用 Authorization header 传 access_token。
        """
        login_response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        access_token = login_response.json()["data"]["access_token"]
        # 清除 cookie,避免 cookie 中的 refresh_token 干扰测试
        client.cookies.clear()
        headers = {"Authorization": f"Bearer {access_token}"}
        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == 401

    def test_get_current_user_info(self, client, auth_headers):
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "id" in data["data"]
        assert "username" in data["data"]
        assert "role" in data["data"]
        assert "email" in data["data"]
        assert data["data"]["username"] == "admin"
        assert data["data"]["role"] == "admin"

    def test_get_current_user_info_no_token(self, client):
        response = client.get("/auth/me")
        assert response.status_code == 401


class TestHealthAPI:
    """健康检查API测试"""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
        assert data["data"]["platform"] == "TestAI"


class TestGovernanceAPI:
    """治理API测试"""

    def test_execute_governance(self, client, auth_headers):
        with patch('src.platform.api.orchestrator.execute_governance_flow') as mock_flow:
            mock_flow.return_value = {"status": "DIAGNOSED"}
            response = client.post(
                "/governance/execute",
                params={"component_name": "test"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "trace_id" in data["data"]

    def test_list_approvals(self, client, auth_headers):
        response = client.get("/governance/approvals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "approvals" in data["data"]

    def test_approve_patch(self, client, auth_headers):
        # P0-2 修复后:approver 参数已移除,approver 强制取认证用户
        from src.governance.approval import ApprovalStatus
        with patch('src.platform.api.orchestrator.approve_and_apply') as mock_approve, \
             patch('src.platform.api.approval_manager.get_approval') as mock_get:
            mock_approve.return_value = {"status": "FIXED"}
            mock_record = MagicMock()
            mock_record.is_expired = False
            mock_record.status = ApprovalStatus.PENDING
            mock_get.return_value = mock_record
            response = client.post(
                "/governance/approvals/tx1/approve",
                headers=auth_headers,
            )
            assert response.status_code == 200
            # 验证 approver 是认证用户,而非查询参数
            call_args = mock_approve.call_args
            assert call_args is not None, "approve_and_apply 必须被调用"
            # approve_and_apply(self, tx_id, approver, reason=None)
            passed_approver = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("approver")
            assert passed_approver == "admin", (
                f"approver 必须从认证用户获取,实际: {passed_approver!r}"
            )

    def test_approve_patch_expired(self, client, auth_headers):
        """审批记录过期时必须返回 400, 且不调用 approve_and_apply。"""
        from src.governance.approval import ApprovalStatus
        with patch('src.platform.api.orchestrator.approve_and_apply') as mock_approve, \
             patch('src.platform.api.approval_manager.get_approval') as mock_get:
            mock_record = MagicMock()
            mock_record.is_expired = True
            mock_record.status = ApprovalStatus.PENDING
            mock_get.return_value = mock_record
            response = client.post(
                "/governance/approvals/tx_expired/approve",
                headers=auth_headers,
            )
            assert response.status_code == 400, (
                f"过期审批应返回 400, 实际: {response.status_code}"
            )
            data = response.json()
            assert "已过期" in data.get("detail", ""), (
                f"错误信息应包含 '已过期', 实际: {data}"
            )
            mock_approve.assert_not_called(), (
                "过期审批不应调用 approve_and_apply"
            )

    def test_reject_patch(self, client, auth_headers):
        # P0-2 修复后:approver 参数已移除,reason 为必填查询参数
        from src.governance.approval import ApprovalStatus
        with patch('src.platform.api.approval_manager.reject') as mock_reject, \
             patch('src.platform.api.approval_manager.get_approval') as mock_get:
            mock_reject.return_value = True
            mock_record = MagicMock()
            mock_record.status = ApprovalStatus.PENDING
            mock_get.return_value = mock_record
            response = client.post(
                "/governance/approvals/tx1/reject",
                params={"reason": "bad patch"},
                headers=auth_headers,
            )
            assert response.status_code == 200


class TestMonitoringAPI:
    """监控API测试"""

    def test_get_alerts(self, client, auth_headers):
        with patch('src.platform.api.alert_manager.get_alerts') as mock_get:
            mock_get.return_value = []
            response = client.get("/monitoring/alerts", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "count" in data["data"]
            assert "alerts" in data["data"]

    def test_get_alerts_by_level(self, client, auth_headers):
        mock_alert = MagicMock()
        mock_alert.get_alerts_by_level = MagicMock(return_value=[])
        mock_alert.get_alerts = MagicMock(return_value=[])
        with patch('src.platform.api.alert_manager', mock_alert):
            response = client.get("/monitoring/alerts?level=INFO", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_acknowledge_alert_success_contract(self, client, auth_headers):
        """正向: acknowledge_alert 返回 True → 200 + 完整契约字段。

        源码契约 (api.py:818-822):
          ApiResponse(success=True, data={"alert_id": alert_id, "acknowledged": True},
                      message="Alert acknowledged")

        反模式修复: 旧版仅断言 success=True, 未验证 data.alert_id / data.acknowledged /
        message, 也未验证 acknowledge_alert 收到的 alert_id 来自路径参数、user_id 来自
        认证用户。弱断言无法发现 "返回 True 但 data 字段缺失/错位" 的回归。
        """
        with patch('src.platform.api.alert_manager.acknowledge_alert') as mock_ack:
            mock_ack.return_value = True
            response = client.post(
                "/monitoring/alerts/alert-xyz-999/acknowledge",
                headers=auth_headers,
            )

        # ---- Assert: HTTP 200 + success=True ----
        assert response.status_code == 200, (
            f"成功 ack 应返回 200, 实际: {response.status_code}, body: {response.text}"
        )
        data = response.json()
        assert data["success"] is True, (
            f"success 必须为 True, 实际: {data.get('success')}"
        )

        # ---- Assert: data 契约字段 (api.py:820) ----
        assert data["data"]["alert_id"] == "alert-xyz-999", (
            f"data.alert_id 必须来自路径参数, 实际: {data['data'].get('alert_id')!r}"
        )
        assert data["data"]["acknowledged"] is True, (
            f"data.acknowledged 必须为 True, 实际: {data['data'].get('acknowledged')!r}"
        )
        assert data["message"] == "Alert acknowledged", (
            f"message 必须为 'Alert acknowledged', 实际: {data.get('message')!r}"
        )

        # ---- Assert: acknowledge_alert 收到正确的 alert_id + 认证用户名 ----
        # acknowledge_alert(alert_id, user_id) — alert_id 来自路径, user_id 来自认证用户
        mock_ack.assert_called_once()
        call_args = mock_ack.call_args
        passed_alert_id = call_args[0][0] if call_args[0] else call_args[1].get("alert_id")
        passed_user_id = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("user_id")
        )
        assert passed_alert_id == "alert-xyz-999", (
            f"alert_id 必须来自路径参数, 实际: {passed_alert_id!r}"
        )
        assert passed_user_id == "admin", (
            f"user_id 必须来自认证用户 (admin), 实际: {passed_user_id!r} — "
            "说明 endpoint 未正确传递 user.username"
        )

    def test_acknowledge_alert_not_found_returns_404(self, client, auth_headers):
        """负向: acknowledge_alert 返回 False → 404 + success=False + error_code。

        源码契约 (api.py:816-817 + 全局异常处理器 194-221):
          HTTPException(status_code=404, detail="Alert not found")
          → {success: False, message: "Alert not found", error_code: "HTTP_404",
             detail: "Alert not found"}

        反模式修复: 旧版无负向测试, 无法发现 BUG-005 类回归
        ("acknowledge_alert 返回 False 仍返回 200 + success=True")。
        """
        with patch('src.platform.api.alert_manager.acknowledge_alert') as mock_ack:
            mock_ack.return_value = False  # alert 不存在
            response = client.post(
                "/monitoring/alerts/nonexistent-alert/acknowledge",
                headers=auth_headers,
            )

        assert response.status_code == 404, (
            f"不存在的 alert 应返回 404, 实际: {response.status_code}, body: {response.text}"
        )
        data = response.json()
        assert data["success"] is False, (
            f"404 响应 success 必须为 False, 实际: {data.get('success')}"
        )
        assert data["error_code"] == "HTTP_404", (
            f"error_code 必须为 'HTTP_404' (全局异常处理器 api.py:209), "
            f"实际: {data.get('error_code')!r}"
        )
        assert "not found" in data["message"].lower(), (
            f"message 应提示 alert 不存在, 实际: {data.get('message')!r}"
        )
        mock_ack.assert_called_once()

    def test_acknowledge_alert_propagates_alert_id_from_path(self, client, auth_headers):
        """边界: 不同 alert_id 路径参数必须原样传递给 acknowledge_alert。

        防止路径参数被忽略或硬编码 (反模式: mock 不校验入参, 掩盖路径解析 bug)。
        """
        with patch('src.platform.api.alert_manager.acknowledge_alert') as mock_ack:
            mock_ack.return_value = True
            response = client.post(
                "/monitoring/alerts/CUSTOM-ID-12345/acknowledge",
                headers=auth_headers,
            )

        assert response.status_code == 200
        received_alert_id = mock_ack.call_args[0][0]
        assert received_alert_id == "CUSTOM-ID-12345", (
            f"路径 alert_id 必须原样传递给 acknowledge_alert, 实际: {received_alert_id!r}"
        )
        assert response.json()["data"]["alert_id"] == "CUSTOM-ID-12345", (
            "响应 data.alert_id 必须与路径参数一致"
        )

    def test_get_metrics(self, client, auth_headers):
        response = client.get("/monitoring/metrics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert "metrics" in data["data"]


class TestWorkflowAPI:
    """工作流API测试"""

    @pytest.mark.parametrize("name,tasks,expected_status", [
        ("Test Workflow", [], 200),
        ("Workflow with tasks", [{"type": "monitoring", "name": "Task 1"}], 200),
        ("", [], 422),
        ("Test", None, 200),
    ])
    def test_define_workflow_various_inputs(self, client, auth_headers, name, tasks, expected_status):
        with patch('src.platform.api.workflow_engine.define_workflow') as mock_define:
            mock_define.return_value = "workflow_001"
            payload = {"name": name}
            if tasks is not None:
                payload["tasks"] = tasks
            response = client.post(
                "/workflow/define",
                json=payload,
                headers=auth_headers,
            )
            assert response.status_code == expected_status
            if expected_status == 200:
                data = response.json()
                assert data["success"] is True
                assert "data" in data
                assert "workflow_id" in data["data"]
                assert data["data"]["workflow_id"] == "workflow_001"

    def test_define_workflow_detailed(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.define_workflow') as mock_define:
            mock_define.return_value = "workflow_001"
            response = client.post(
                "/workflow/define",
                json={
                    "name": "Test Workflow",
                    "description": "Test Description",
                    "tasks": [
                        {"type": "monitoring", "name": "Check Status", "params": {"action": "get_status"}},
                        {"type": "approval", "name": "Approve", "params": {"tx_id": "test"}},
                    ],
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "workflow_id" in data["data"]
            assert data["data"]["workflow_id"] == "workflow_001"
            mock_define.assert_called_once()

    def test_define_workflow_no_auth(self, client):
        response = client.post(
            "/workflow/define",
            json={"name": "Test Workflow", "tasks": []},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("workflow_id,expected_status,expected_success", [
        ("workflow_001", 200, True),
        ("nonexistent", 200, False),
        ("", 404, False),
    ])
    def test_execute_workflow_various(self, client, auth_headers, workflow_id, expected_status, expected_success):
        with patch('src.platform.api.workflow_engine.execute_workflow') as mock_execute:
            if workflow_id == "nonexistent":
                mock_execute.return_value = {"status": "failed", "error": "Workflow not found"}
            else:
                mock_execute.return_value = {"status": "completed", "instance_id": "inst_001"}
            response = client.post(
                f"/workflow/{workflow_id}/execute",
                headers=auth_headers,
            )
            assert response.status_code == expected_status
            if expected_status == 200:
                data = response.json()
                assert data["success"] is expected_success
                if expected_success:
                    assert "data" in data
                    assert "status" in data["data"]
                    assert "instance_id" in data["data"]
                else:
                    assert "message" in data
                    assert "Workflow not found" in data["message"]

    def test_execute_workflow_with_params(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.execute_workflow') as mock_execute:
            mock_execute.return_value = {"status": "completed", "instance_id": "inst_001"}
            response = client.post(
                "/workflow/workflow_001/execute",
                json={"params": {"env": "test"}},
                headers=auth_headers,
            )
            assert response.status_code == 200

    @pytest.mark.parametrize("instance_id,expected_status", [
        ("inst_001", 200),
        ("nonexistent", 404),
        ("invalid-id", 404),
    ])
    def test_get_workflow_status_various(self, client, auth_headers, instance_id, expected_status):
        with patch('src.platform.api.workflow_engine.get_workflow_status') as mock_status:
            if instance_id == "nonexistent" or instance_id == "invalid-id":
                mock_status.return_value = None
            else:
                mock_status.return_value = {"status": "completed", "instance_id": instance_id}
            response = client.get(f"/workflow/{instance_id}/status", headers=auth_headers)
            assert response.status_code == expected_status
            if expected_status == 200:
                data = response.json()
                assert data["success"] is True
                assert "data" in data
                assert "status" in data["data"]
                assert "instance_id" in data["data"]

    def test_get_workflow_status_no_auth(self, client):
        response = client.get("/workflow/inst_001/status")
        assert response.status_code == 401


class TestConfigAPI:
    """配置API测试"""

    def test_get_config(self, client, auth_headers):
        response = client.get("/config", headers=auth_headers)
        assert response.status_code == 200

    def test_get_config_section(self, client, auth_headers):
        response = client.get("/config?section=platform", headers=auth_headers)
        assert response.status_code == 200

    def test_update_config(self, client, auth_headers):
        response = client.put(
            "/config/api",
            json={"port": 8080},
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestDashboardAPI:
    """仪表盘API测试"""

    def test_get_dashboard_summary(self, client, auth_headers):
        with patch('src.platform.api.dashboard_service.get_summary') as mock_summary:
            mock_summary.return_value = {"alerts": {"unacknowledged": 0}}
            response = client.get("/dashboard/summary", headers=auth_headers)
            assert response.status_code == 200

    def test_get_quality_trend(self, client, auth_headers):
        response = client.get("/dashboard/quality-trend", headers=auth_headers)
        assert response.status_code == 200


class TestUsersAPI:
    """用户API测试"""

    def test_list_users(self, client, auth_headers):
        response = client.get("/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "users" in data["data"]

    def test_list_users_filtered(self, client, auth_headers):
        response = client.get("/users?role=admin", headers=auth_headers)
        assert response.status_code == 200

    def test_create_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.create_user') as mock_create:
            mock_create.return_value = MagicMock(
                user_id="user_001",
                username="testuser",
                email="test@test.com",
            )
            response = client.post(
                "/users",
                json={"username": "testuser", "email": "test@test.com"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_create_user_duplicate(self, client, auth_headers):
        with patch('src.platform.api.user_manager.create_user') as mock_create:
            mock_create.side_effect = ValueError("Username already exists")
            response = client.post(
                "/users",
                json={"username": "admin", "email": "test@test.com"},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_get_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.get_user') as mock_get:
            mock_get.return_value = MagicMock(
                user_id="user_001",
                username="testuser",
                email="test@test.com",
                role=MagicMock(value="admin"),
                status=MagicMock(value="active"),
                full_name="Test User",
                department="IT",
                created_at=MagicMock(isoformat=lambda: "2024-01-01"),
                last_login_at=None,
            )
            response = client.get("/users/user_001", headers=auth_headers)
            assert response.status_code == 200

    def test_get_user_not_found(self, client, auth_headers):
        with patch('src.platform.api.user_manager.get_user') as mock_get:
            mock_get.return_value = None
            response = client.get("/users/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_update_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.update_user') as mock_update:
            mock_update.return_value = MagicMock(user_id="user_001")
            response = client.put(
                "/users/user_001",
                json={"full_name": "Updated Name"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_update_user_not_found(self, client, auth_headers):
        with patch('src.platform.api.user_manager.update_user') as mock_update:
            mock_update.return_value = None
            response = client.put(
                "/users/nonexistent",
                json={"full_name": "Updated Name"},
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_delete_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.delete_user') as mock_delete:
            mock_delete.return_value = True
            response = client.delete("/users/user_001", headers=auth_headers)
            assert response.status_code == 200

    def test_delete_user_not_found(self, client, auth_headers):
        with patch('src.platform.api.user_manager.delete_user') as mock_delete:
            mock_delete.return_value = False
            response = client.delete("/users/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_activate_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.activate_user') as mock_activate:
            mock_activate.return_value = MagicMock(user_id="user_001")
            response = client.post("/users/user_001/activate", headers=auth_headers)
            assert response.status_code == 200

    def test_activate_user_not_found(self, client, auth_headers):
        with patch('src.platform.api.user_manager.activate_user') as mock_activate:
            mock_activate.return_value = None
            response = client.post("/users/nonexistent/activate", headers=auth_headers)
            assert response.status_code == 404

    def test_suspend_user(self, client, auth_headers):
        with patch('src.platform.api.user_manager.suspend_user') as mock_suspend:
            mock_suspend.return_value = MagicMock(user_id="user_001")
            response = client.post("/users/user_001/suspend", headers=auth_headers)
            assert response.status_code == 200

    def test_suspend_user_not_found(self, client, auth_headers):
        with patch('src.platform.api.user_manager.suspend_user') as mock_suspend:
            mock_suspend.return_value = None
            response = client.post("/users/nonexistent/suspend", headers=auth_headers)
            assert response.status_code == 404


class TestTeamsAPI:
    """团队API测试"""

    def test_list_teams(self, client, auth_headers):
        response = client.get("/teams", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "teams" in data["data"]

    def test_create_team(self, client, auth_headers):
        with patch('src.platform.api.team_manager.create_team') as mock_create:
            mock_create.return_value = MagicMock(
                team_id="team_001",
                name="Test Team",
            )
            response = client.post(
                "/teams",
                json={"name": "Test Team"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_create_team_duplicate(self, client, auth_headers):
        with patch('src.platform.api.team_manager.create_team') as mock_create:
            mock_create.side_effect = ValueError("Team already exists")
            response = client.post(
                "/teams",
                json={"name": "Test Team"},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_get_team(self, client, auth_headers):
        with patch('src.platform.api.team_manager.get_team') as mock_get:
            mock_get.return_value = MagicMock(
                team_id="team_001",
                name="Test Team",
                description="Test",
                members=[],
                created_at=MagicMock(isoformat=lambda: "2024-01-01"),
                updated_at=MagicMock(isoformat=lambda: "2024-01-01"),
            )
            response = client.get("/teams/team_001", headers=auth_headers)
            assert response.status_code == 200

    def test_get_team_not_found(self, client, auth_headers):
        with patch('src.platform.api.team_manager.get_team') as mock_get:
            mock_get.return_value = None
            response = client.get("/teams/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_update_team(self, client, auth_headers):
        with patch('src.platform.api.team_manager.update_team') as mock_update:
            mock_update.return_value = MagicMock(team_id="team_001")
            response = client.put(
                "/teams/team_001",
                json={"name": "Updated Team"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_update_team_not_found(self, client, auth_headers):
        with patch('src.platform.api.team_manager.update_team') as mock_update:
            mock_update.return_value = None
            response = client.put(
                "/teams/nonexistent",
                json={"name": "Updated Team"},
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_delete_team(self, client, auth_headers):
        with patch('src.platform.api.team_manager.delete_team') as mock_delete:
            mock_delete.return_value = True
            response = client.delete("/teams/team_001", headers=auth_headers)
            assert response.status_code == 200

    def test_delete_team_not_found(self, client, auth_headers):
        with patch('src.platform.api.team_manager.delete_team') as mock_delete:
            mock_delete.return_value = False
            response = client.delete("/teams/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_add_team_member(self, client, auth_headers):
        with patch('src.platform.api.team_manager.add_member') as mock_add:
            mock_add.return_value = MagicMock(team_id="team_001")
            response = client.post(
                "/teams/team_001/members",
                json={"user_id": "user_001", "username": "user1", "role": "MEMBER"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_add_team_member_invalid(self, client, auth_headers):
        response = client.post(
            "/teams/team_001/members",
            json={"user_id": "user_001", "username": "user1", "role": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_remove_team_member(self, client, auth_headers):
        with patch('src.platform.api.team_manager.remove_member') as mock_remove:
            mock_remove.return_value = MagicMock(team_id="team_001")
            response = client.delete("/teams/team_001/members/user_001", headers=auth_headers)
            assert response.status_code == 200

    def test_remove_team_member_not_found(self, client, auth_headers):
        with patch('src.platform.api.team_manager.remove_member') as mock_remove:
            mock_remove.return_value = None
            response = client.delete("/teams/team_001/members/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_get_team_members(self, client, auth_headers):
        with patch('src.platform.api.team_manager.get_team_members') as mock_get:
            mock_get.return_value = []
            response = client.get("/teams/team_001/members", headers=auth_headers)
            assert response.status_code == 200


class TestTrackerAPI:
    """治理追踪器API测试"""

    def test_get_tracker_events(self, client, auth_headers):
        response = client.get("/governance/tracker/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "events" in data["data"]

    def test_get_tracker_events_filtered(self, client, auth_headers):
        response = client.get(
            "/governance/tracker/events?trace_id=test&event_type=DIAGNOSE_START",
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_get_tracker_summary(self, client, auth_headers):
        response = client.get("/governance/tracker/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "total_events" in data["data"]


class TestBaselinesAPI:
    """基线管理API测试"""

    def test_get_baselines(self, client, auth_headers):
        mock_baseline = MagicMock()
        mock_baseline.get_all_baselines = MagicMock(return_value=[])
        with patch('src.platform.api.baseline_manager', mock_baseline):
            response = client.get("/governance/baselines", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "count" in data["data"]
            assert "baselines" in data["data"]

    def test_get_baseline(self, client, auth_headers):
        with patch('src.platform.api.baseline_manager.get_baseline') as mock_get:
            mock_get.return_value = {"baseline_id": "test", "name": "Test"}
            response = client.get("/governance/baselines/test", headers=auth_headers)
            assert response.status_code == 200

    def test_get_baseline_not_found(self, client, auth_headers):
        with patch('src.platform.api.baseline_manager.get_baseline') as mock_get:
            mock_get.return_value = None
            response = client.get("/governance/baselines/nonexistent", headers=auth_headers)
            assert response.status_code == 404

    def test_validate_baseline(self, client, auth_headers):
        with patch('src.platform.api.baseline_manager.validate_against_baseline') as mock_validate:
            mock_validate.return_value = {
                "passed": True,
                "convergence_score": 1.0,
                "mismatches": [],
            }
            response = client.post(
                "/governance/baselines/test/validate",
                json={"data": {"value": 100}},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_get_baseline_convergence(self, client, auth_headers):
        with patch('src.platform.api.baseline_manager.get_baseline') as mock_get:
            mock_record = MagicMock()
            mock_record.data = {
                "expected_output": {"value": 100},
                "tolerance": 0.0,
            }
            mock_get.return_value = mock_record
            response = client.get("/governance/baselines/test/convergence", headers=auth_headers)
            assert response.status_code == 200

    def test_get_baseline_convergence_not_found(self, client, auth_headers):
        with patch('src.platform.api.baseline_manager.get_baseline') as mock_get:
            mock_get.return_value = None
            response = client.get("/governance/baselines/nonexistent/convergence", headers=auth_headers)
            assert response.status_code == 404


class TestAPIAuthorization:
    """API授权测试"""

    def test_unauthorized_access(self, client):
        response = client.get("/users")
        assert response.status_code == 401

    def test_invalid_token(self, client):
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/users", headers=headers)
        assert response.status_code == 401

    def test_insufficient_permissions(self, client):
        response = client.post("/auth/login", json={"username": "viewer", "password": "password"})
        token = response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/users", json={"username": "test", "email": "test@test.com"}, headers=headers)
        assert response.status_code == 403
