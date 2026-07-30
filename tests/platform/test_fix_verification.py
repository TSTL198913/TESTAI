"""专项测试用例 - 验证本轮修复的正确性

修复清单:
1. API契约一致性 - get_config 返回 ApiResponse 格式
2. 工作流幂等性 - 并发执行相同工作流不会创建重复实例(TOCTOU修复)
3. 审批幂等性 - approve_and_apply 检查审批状态避免重复处理
4. 输入校验 - CreateUserRequest(email) 和 CreateTeamRequest(name) 校验
"""
import threading
import pytest
from fastapi.testclient import TestClient

from src.platform.api import app
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType
from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.models import DiagnosticContext, PatchProposal, PatchType


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    login_resp = client.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAPIResponseFormatFix:
    """修复验证: API契约一致性 - get_config 返回 ApiResponse 格式

    修复前: get_config 返回裸 dict,违反平台统一响应格式
    修复后: get_config 返回 ApiResponse 格式 {success, data, message, error_code}
    """

    def test_get_config_returns_api_response(self, client, auth_headers):
        """get_config 必须返回 ApiResponse 格式,而非裸 dict"""
        response = client.get("/config", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()

        assert "success" in body, (
            f"响应必须是 ApiResponse 格式(含 success), 实际: {body}"
        )
        assert body["success"] is True
        assert "data" in body, f"ApiResponse 必须包含 data 字段, 实际: {body}"
        assert "message" in body, f"ApiResponse 必须包含 message 字段, 实际: {body}"

    def test_get_config_section_returns_api_response(self, client, auth_headers):
        """get_config?section=xxx 必须返回 ApiResponse 格式"""
        response = client.get("/config?section=test", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()

        assert "success" in body, (
            f"响应必须是 ApiResponse 格式(含 success), 实际: {body}"
        )
        assert body["success"] is True
        assert "data" in body, f"ApiResponse 必须包含 data 字段, 实际: {body}"


class TestWorkflowIdempotencyFix:
    """修复验证: 工作流幂等性 - TOCTOU竞态条件修复

    修复前: 检查实例状态和创建实例不是原子操作,高并发下可能创建多个RUNNING实例
    修复后: 将实例创建和状态设置移至锁保护范围内,确保原子性
    """

    @pytest.mark.asyncio
    async def test_concurrent_execute_workflow_no_duplicate_instances(self):
        """并发执行同一工作流不应创建重复的RUNNING实例"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.DELAY, name="Delay Task", params={"seconds": 0.5}),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)

        results = []

        async def execute_task():
            result = await engine.execute_workflow(workflow_id)
            results.append(result)

        import asyncio
        tasks = [execute_task() for _ in range(5)]
        await asyncio.gather(*tasks)

        running_count = sum(
            1 for inst in engine.instances.values()
            if inst.workflow_id == workflow_id and inst.status.value == "running"
        )

        assert running_count <= 1, (
            f"同一工作流不应有多个RUNNING实例,实际: {running_count}"
        )

        failed_count = sum(1 for r in results if r.get("status") == "failed")
        completed_count = sum(1 for r in results if r.get("status") == "completed")

        assert failed_count + completed_count == 5, (
            f"总请求数应为5,实际failed={failed_count},completed={completed_count}"
        )

    @pytest.mark.asyncio
    async def test_execute_running_workflow_returns_failed(self):
        """执行已在运行的工作流应返回失败

        使用线程模拟并发：第一个线程启动执行（设置RUNNING状态），
        第二个线程在第一个线程完成前尝试执行，应返回失败。
        """
        from unittest.mock import patch
        import asyncio
        
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="Monitor Task", params={"action": "get_status"}),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)

        event = asyncio.Event()
        
        async def blocking_execute():
            """模拟长时间运行的执行"""
            with patch.object(engine, '_execute_task') as mock_execute:
                async def slow_execution(*args, **kwargs):
                    event.set()
                    await asyncio.sleep(0.5)
                    return {"status": "completed"}
                
                mock_execute.side_effect = slow_execution
                await engine.execute_workflow(workflow_id)

        async def check_running():
            """等待第一个执行设置RUNNING状态后立即尝试执行"""
            await event.wait()
            await asyncio.sleep(0.05)
            result = await engine.execute_workflow(workflow_id)
            return result

        results = await asyncio.gather(blocking_execute(), check_running())
        second_result = results[1]

        assert second_result["status"] == "failed", (
            f"第二个请求应返回failed,实际: {second_result}"
        )
        assert "already running" in second_result.get("error", ""), (
            f"应提示已在运行,实际: {second_result}"
        )


class TestApprovalIdempotencyFix:
    """修复验证: 审批幂等性 - approve_and_apply 检查审批状态

    修复前: approve_and_apply 未检查审批记录状态,可能重复处理已完成的审批
    修复后: 处理前检查审批状态,非PENDING状态拒绝处理
    """

    def setup_method(self):
        """清理单例状态"""
        approval_mgr = ApprovalManager()
        approval_mgr._approvals.clear()

    @pytest.mark.asyncio
    async def test_approve_and_apply_already_approved(self):
        """对已批准的审批记录再次调用 approve_and_apply 应返回失败"""
        orchestrator = GovernanceOrchestrator()
        approval_mgr = ApprovalManager()

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        approval_mgr.create_approval("tx_idempotency_test", proposal, context)
        approval_mgr.approve("tx_idempotency_test", "tech_committee")

        result = await orchestrator.approve_and_apply("tx_idempotency_test", "tech_committee")

        assert result["status"] == "FAILED", (
            f"已批准的审批再次处理应返回FAILED,实际: {result}"
        )
        assert "already processed" in result.get("reason", ""), (
            f"应提示已处理,实际: {result}"
        )

    @pytest.mark.asyncio
    async def test_approve_and_apply_already_rejected(self):
        """对已拒绝的审批记录调用 approve_and_apply 应返回失败"""
        orchestrator = GovernanceOrchestrator()
        approval_mgr = ApprovalManager()

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        approval_mgr.create_approval("tx_idempotency_rejected", proposal, context)
        approval_mgr.reject("tx_idempotency_rejected", "tech_committee", "Rejected")

        result = await orchestrator.approve_and_apply("tx_idempotency_rejected", "tech_committee")

        assert result["status"] == "FAILED", (
            f"已拒绝的审批处理应返回FAILED,实际: {result}"
        )
        assert "already processed" in result.get("reason", ""), (
            f"应提示已处理,实际: {result}"
        )


class TestInputValidationFix:
    """修复验证: 输入校验 - email格式和team name长度校验

    修复前: create_user 允许无效email格式, create_team 允许空或过长名称
    修复后: 添加 Pydantic field_validator 进行强校验
    """

    def test_create_user_invalid_email(self, client, auth_headers):
        """创建用户时提供无效email格式应返回422错误"""
        response = client.post(
            "/users",
            json={
                "username": "testuser",
                "email": "invalid-email",
                "role": "tester",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422, (
            f"无效email应返回422,实际: {response.status_code}"
        )
        body = response.json()
        assert "detail" in body or "message" in body

    def test_create_user_valid_email(self, client, auth_headers):
        """创建用户时提供有效email格式应成功"""
        import uuid
        unique_username = f"testuser_{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/users",
            json={
                "username": unique_username,
                "email": f"{unique_username}@example.com",
                "role": "tester",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200, (
            f"有效email应返回200,实际: {response.status_code}, body: {response.text}"
        )
        body = response.json()
        assert body.get("success") is True

    def test_create_team_empty_name(self, client, auth_headers):
        """创建团队时提供空名称应返回422错误"""
        response = client.post(
            "/teams",
            json={
                "name": "",
                "description": "Test team",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422, (
            f"空团队名称应返回422,实际: {response.status_code}"
        )

    def test_create_team_too_long_name(self, client, auth_headers):
        """创建团队时提供过长名称应返回422错误"""
        long_name = "a" * 101
        response = client.post(
            "/teams",
            json={
                "name": long_name,
                "description": "Test team",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422, (
            f"过长团队名称应返回422,实际: {response.status_code}"
        )

    def test_create_team_valid_name(self, client, auth_headers):
        """创建团队时提供有效名称应成功"""
        import uuid
        unique_name = f"Valid Team Name {uuid.uuid4().hex[:8]}"
        response = client.post(
            "/teams",
            json={
                "name": unique_name,
                "description": "Test team",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200, (
            f"有效团队名称应返回200,实际: {response.status_code}, body: {response.text}"
        )
        body = response.json()
        assert body.get("success") is True