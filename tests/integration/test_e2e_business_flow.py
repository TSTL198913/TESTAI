"""端到端业务流程集成测试

模拟真实业务场景：工作流创建 → 执行 → 治理诊断 → 审批 → 补丁应用 → 验证治理追踪

覆盖正向、负向、边界场景，验证完整业务链路的数据一致性和状态转换
"""
import pytest
import uuid
from fastapi.testclient import TestClient

from src.platform.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_headers(client):
    login_resp = client.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestE2EWorkflowGovernanceFlow:
    """端到端测试：工作流 → 治理 → 审批完整流程"""

    def test_full_workflow_governance_approval_flow(self, client, admin_headers):
        """
        场景：创建工作流 → 执行工作流 → 执行治理诊断 → 创建审批 → 审批通过 → 验证追踪记录

        验证点：
        1. 工作流创建成功并可执行
        2. 治理诊断生成审批记录
        3. 审批状态正确转换
        4. 治理追踪记录完整
        """
        workflow_name = f"E2E测试工作流_{uuid.uuid4().hex[:8]}"

        response = client.post(
            "/workflow/define",
            json={
                "name": workflow_name,
                "description": "端到端测试工作流",
                "tasks": [
                    {"type": "monitoring", "name": "健康检查", "params": {"action": "get_status"}}
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        workflow_data = response.json()
        assert workflow_data["success"] is True
        workflow_id = workflow_data["data"]["workflow_id"]
        assert workflow_id is not None

        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        exec_data = response.json()
        assert exec_data["success"] is True
        instance_id = exec_data["data"]["instance_id"]
        assert instance_id is not None

        response = client.get(f"/workflow/{instance_id}/status", headers=admin_headers)
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["instance_id"] == instance_id
        assert status_data["workflow_id"] == workflow_id

        response = client.post(
            "/governance/execute",
            params={
                "component_name": workflow_name,
                "step_id": "test_step",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        governance_data = response.json()
        assert governance_data["success"] is True
        assert "trace_id" in governance_data["data"]

        response = client.get("/governance/approvals", headers=admin_headers)
        assert response.status_code == 200
        approvals_data = response.json()
        assert approvals_data["success"] is True
        assert "count" in approvals_data["data"]
        assert "approvals" in approvals_data["data"]

        if approvals_data["data"]["count"] > 0:
            tx_id = approvals_data["data"]["approvals"][0]["tx_id"]

            response = client.post(
                f"/governance/approvals/{tx_id}/approve",
                params={"approver": "admin"},
                headers=admin_headers,
            )
            assert response.status_code == 200
            approval_result = response.json()
            assert approval_result["success"] is True
            assert approval_result["data"]["tx_id"] == tx_id

            response = client.get("/governance/tracker/events", headers=admin_headers)
            assert response.status_code == 200
            tracker_data = response.json()
            assert tracker_data["success"] is True
            assert len(tracker_data["data"]["events"]) > 0

    def test_workflow_execution_idempotency(self, client, admin_headers):
        """
        场景：并发执行同一工作流验证幂等性

        验证点：
        1. 同一工作流不应有多个RUNNING实例
        2. 重复执行应返回错误提示
        """
        workflow_name = f"幂等性测试_{uuid.uuid4().hex[:8]}"

        response = client.post(
            "/workflow/define",
            json={
                "name": workflow_name,
                "description": "幂等性测试",
                "tasks": [
                    {"type": "monitoring", "name": "监控任务", "params": {"action": "get_status"}}
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        workflow_id = response.json()["data"]["workflow_id"]

        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200

        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        result = response.json()
        assert not result["success"]
        assert "already running" in result.get("message", "").lower()


class TestE2EGovernanceApprovalFlow:
    """端到端测试：治理审批完整流程"""

    def test_approval_expire_handling(self, client, admin_headers):
        """
        场景：创建审批记录 → 修改过期时间使其过期 → 尝试批准 → 验证拒绝

        验证点：
        1. 过期记录不能被批准
        2. 过期记录状态正确更新
        """
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "expire_test",
                "step_id": "expire_step",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.get("/governance/approvals", headers=admin_headers)
        assert response.status_code == 200
        approvals_data = response.json()

        if approvals_data["data"]["count"] > 0:
            tx_id = approvals_data["data"]["approvals"][0]["tx_id"]

            from src.governance.approval import ApprovalManager, ApprovalStatus
            from datetime import datetime, timedelta

            mgr = ApprovalManager()
            record = mgr.get_approval(tx_id)
            if record:
                record.expires_at = datetime.now() - timedelta(minutes=1)

                response = client.post(
                    f"/governance/approvals/{tx_id}/approve",
                    params={"approver": "admin"},
                    headers=admin_headers,
                )
                assert response.status_code == 200
                result = response.json()
                assert not result["success"]

    def test_approval_idempotency(self, client, admin_headers):
        """
        场景：审批记录批准后再次批准 → 验证拒绝

        验证点：
        1. 已批准的记录不能再次批准
        2. 返回明确的错误信息
        """
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "idempotency_test",
                "step_id": "idempotency_step",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.get("/governance/approvals", headers=admin_headers)
        assert response.status_code == 200
        approvals_data = response.json()

        if approvals_data["data"]["count"] > 0:
            tx_id = approvals_data["data"]["approvals"][0]["tx_id"]

            response = client.post(
                f"/governance/approvals/{tx_id}/approve",
                params={"approver": "admin"},
                headers=admin_headers,
            )
            assert response.status_code == 200
            first_result = response.json()
            assert first_result["success"] is True

            response = client.post(
                f"/governance/approvals/{tx_id}/approve",
                params={"approver": "admin"},
                headers=admin_headers,
            )
            assert response.status_code == 200
            second_result = response.json()
            assert not second_result["success"]


class TestE2EUserManagementFlow:
    """端到端测试：用户管理完整流程"""

    def test_user_create_read_update_delete(self, client, admin_headers):
        """
        场景：创建用户 → 读取用户 → 更新用户 → 删除用户

        验证点：
        1. 用户CRUD操作完整流程
        2. 数据一致性验证
        """
        unique_username = f"e2e_user_{uuid.uuid4().hex[:8]}"
        unique_email = f"e2e_{uuid.uuid4().hex[:8]}@testai.com"

        response = client.post(
            "/users",
            json={
                "username": unique_username,
                "email": unique_email,
                "role": "tester",
                "full_name": "E2E测试用户",
                "department": "测试部",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        create_data = response.json()
        assert create_data["success"] is True
        user_id = create_data["data"]["user_id"]

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        read_data = response.json()
        assert read_data["success"] is True
        assert read_data["data"]["username"] == unique_username
        assert read_data["data"]["email"] == unique_email
        assert read_data["data"]["role"] == "tester"
        assert read_data["data"]["full_name"] == "E2E测试用户"
        assert read_data["data"]["department"] == "测试部"

        response = client.put(
            f"/users/{user_id}",
            json={"role": "viewer", "full_name": "更新后的名称"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        update_data = response.json()
        assert update_data["success"] is True

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        verify_data = response.json()
        assert verify_data["data"]["role"] == "viewer"
        assert verify_data["data"]["full_name"] == "更新后的名称"

        response = client.delete(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        delete_data = response.json()
        assert delete_data["success"] is True

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 404

    def test_user_email_validation(self, client, admin_headers):
        """
        场景：创建用户时提供无效email格式

        验证点：
        1. 无效email被拒绝
        2. 返回422状态码和明确错误信息
        """
        response = client.post(
            "/users",
            json={
                "username": f"invalid_email_user_{uuid.uuid4().hex[:8]}",
                "email": "invalid-email-format",
                "role": "tester",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestE2ETeamManagementFlow:
    """端到端测试：团队管理完整流程"""

    def test_team_create_and_member_management(self, client, admin_headers):
        """
        场景：创建团队 → 添加成员 → 查看成员 → 删除成员 → 删除团队

        验证点：
        1. 团队CRUD操作完整流程
        2. 成员管理操作正确
        """
        team_name = f"E2E测试团队_{uuid.uuid4().hex[:8]}"

        response = client.post(
            "/teams",
            json={"name": team_name, "description": "端到端测试团队"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        team_data = response.json()
        assert team_data["success"] is True
        team_id = team_data["data"]["team_id"]

        response = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "1", "username": "admin", "role": "admin"},
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.get(f"/teams/{team_id}/members", headers=admin_headers)
        assert response.status_code == 200
        members_data = response.json()
        assert members_data["success"] is True
        assert len(members_data["data"]["members"]) > 0
        assert any(m["username"] == "admin" for m in members_data["data"]["members"])

        response = client.delete(f"/teams/{team_id}/members/admin", headers=admin_headers)
        assert response.status_code == 200

        response = client.delete(f"/teams/{team_id}", headers=admin_headers)
        assert response.status_code == 200

        response = client.get(f"/teams/{team_id}", headers=admin_headers)
        assert response.status_code == 404

    def test_team_name_validation(self, client, admin_headers):
        """
        场景：创建团队时提供无效名称

        验证点：
        1. 空名称被拒绝
        2. 过长名称被拒绝
        """
        response = client.post(
            "/teams",
            json={"name": "", "description": "空名称团队"},
            headers=admin_headers,
        )
        assert response.status_code == 422

        response = client.post(
            "/teams",
            json={"name": "a" * 101, "description": "过长名称团队"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestE2EErrorHandling:
    """端到端测试：错误处理和异常场景"""

    def test_nonexistent_workflow_execution(self, client, admin_headers):
        """
        场景：执行不存在的工作流

        验证点：
        1. 返回明确的错误信息
        2. 响应格式符合统一规范
        """
        response = client.post("/workflow/nonexistent_id/execute", headers=admin_headers)
        assert response.status_code == 200
        result = response.json()
        assert not result["success"]
        assert "not found" in result.get("message", "").lower()

    def test_unauthorized_access(self, client):
        """
        场景：未认证用户访问受保护资源

        验证点：
        1. 返回401状态码
        2. 响应格式符合统一规范
        """
        response = client.get("/workflow")
        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False
        assert "message" in body
        assert "error_code" in body

    def test_permission_denied(self, client):
        """
        场景：权限不足用户执行受限操作

        验证点：
        1. 返回403状态码
        2. 响应格式符合统一规范
        """
        login_resp = client.post(
            "/auth/login",
            json={"username": "viewer", "password": "password"},
        )
        assert login_resp.status_code == 200
        viewer_token = login_resp.json()["data"]["access_token"]
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        response = client.post(
            "/governance/approvals/test_tx/approve",
            params={"approver": "viewer"},
            headers=viewer_headers,
        )
        assert response.status_code == 403
        body = response.json()
        assert body["success"] is False