import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.platform.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "password"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAuthAPI:
    """认证API测试"""

    def test_login_success(self, client):
        response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data

    def test_login_invalid_credentials(self, client):
        response = client.post("/auth/login", json={"username": "admin", "password": "wrong_password"})
        assert response.status_code == 401

    def test_refresh_token(self, client):
        login_response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        refresh_token = login_response.json()["refresh_token"]
        headers = {"Authorization": f"Bearer {refresh_token}"}
        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_refresh_token_invalid(self, client):
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == 401

    def test_get_current_user_info(self, client, auth_headers):
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "role" in data


class TestHealthAPI:
    """健康检查API测试"""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["platform"] == "TestAI"


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
            assert "trace_id" in response.json()

    def test_list_approvals(self, client, auth_headers):
        response = client.get("/governance/approvals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "approvals" in data

    def test_approve_patch(self, client, auth_headers):
        with patch('src.platform.api.orchestrator.approve_and_apply') as mock_approve:
            mock_approve.return_value = {"status": "FIXED"}
            response = client.post(
                "/governance/approvals/tx1/approve",
                params={"approver": "admin"},
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_reject_patch(self, client, auth_headers):
        with patch('src.platform.api.approval_manager.reject') as mock_reject:
            mock_reject.return_value = True
            response = client.post(
                "/governance/approvals/tx1/reject",
                params={"approver": "admin", "reason": "bad patch"},
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
            assert "count" in data
            assert "alerts" in data

    def test_get_alerts_by_level(self, client, auth_headers):
        mock_alert = MagicMock()
        mock_alert.get_alerts_by_level = MagicMock(return_value=[])
        mock_alert.get_alerts = MagicMock(return_value=[])
        with patch('src.platform.api.alert_manager', mock_alert):
            response = client.get("/monitoring/alerts?level=INFO", headers=auth_headers)
            assert response.status_code == 200

    def test_acknowledge_alert(self, client, auth_headers):
        with patch('src.platform.api.alert_manager.acknowledge_alert') as mock_ack:
            mock_ack.return_value = True
            response = client.post("/monitoring/alerts/alert1/acknowledge", headers=auth_headers)
            assert response.status_code == 200

    def test_get_metrics(self, client, auth_headers):
        response = client.get("/monitoring/metrics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "metrics" in data


class TestWorkflowAPI:
    """工作流API测试"""

    def test_define_workflow(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.define_workflow') as mock_define:
            mock_define.return_value = "workflow_001"
            response = client.post(
                "/workflow/define",
                json={"name": "Test Workflow", "tasks": []},
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert response.json()["workflow_id"] == "workflow_001"

    def test_execute_workflow(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.execute_workflow') as mock_execute:
            mock_execute.return_value = {"status": "completed"}
            response = client.post(
                "/workflow/workflow_001/execute",
                headers=auth_headers,
            )
            assert response.status_code == 200

    def test_get_workflow_status(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.get_workflow_status') as mock_status:
            mock_status.return_value = {"status": "completed"}
            response = client.get("/workflow/workflow_001/status", headers=auth_headers)
            assert response.status_code == 200

    def test_get_workflow_status_not_found(self, client, auth_headers):
        with patch('src.platform.api.workflow_engine.get_workflow_status') as mock_status:
            mock_status.return_value = None
            response = client.get("/workflow/nonexistent/status", headers=auth_headers)
            assert response.status_code == 404


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
        assert "count" in data
        assert "users" in data

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
        assert "count" in data
        assert "teams" in data

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
        assert "count" in data
        assert "events" in data

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
        assert "total_events" in data


class TestBaselinesAPI:
    """基线管理API测试"""

    def test_get_baselines(self, client, auth_headers):
        mock_baseline = MagicMock()
        mock_baseline.get_all_baselines = MagicMock(return_value=[])
        with patch('src.platform.api.baseline_manager', mock_baseline):
            response = client.get("/governance/baselines", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "count" in data
            assert "baselines" in data

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
            mock_get.return_value = {
                "baseline_id": "test",
                "expected_output": {"value": 100},
                "tolerance": 0.0,
            }
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
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/users", json={"username": "test", "email": "test@test.com"}, headers=headers)
        assert response.status_code == 403
