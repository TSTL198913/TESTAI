"""端到端业务流程集成测试

模拟真实业务场景：工作流创建 → 执行 → 治理诊断 → 审批 → 补丁应用 → 验证治理追踪

覆盖正向、负向、边界场景，验证完整业务链路的数据一致性和状态转换
"""
import pytest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.platform.api import app
from src.governance.models import AIGovernanceResult, PatchProposal
from src.governance.registry import PatchType


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


@pytest.fixture
def governance_mock_setup(tmp_path):
    """治理流程 mock 环境: 使补丁可真实应用到临时文件。

    旧版假绿根因:
      /governance/execute 不传 actual_output/expected_baseline →
      _classify_exception 返回 MANUAL_REQUIRED → SKIPPED → 无审批创建 →
      if count > 0 静默跳过所有断言 → 假绿。
      且用 approvals[0] 取 stale 审批, 补丁目标文件不存在 → 审批失败。

    Mock 组件 (per 用户规则: 测试环境强制 mock LLM):
      - orchestrator.agent.analyze_with_context: 返回针对 target_func 的诊断
      - orchestrator._resolve_file_path: 指向临时文件 (路径解析有独立单元测试)
      - orchestrator.executor._path_validator.validate_path: 绕过路径校验 (tmp_path 不在 ALLOWED_DIRS)
      - orchestrator.git_mgr: 避免操作真实 git 仓库 (git 事务有独立单元测试)

    真实组件 (不 mock):
      - GovernanceOrchestrator 六步编排
      - ApprovalManager 审批逻辑 (requires_approval 基于 patch_type)
      - GovernanceTracker 事件记录
      - GovernanceExecutor libcst 补丁应用 (真实修改临时文件)
    """
    from src.platform.api import orchestrator

    # 创建临时目标文件, 含一个真实函数供补丁替换
    target_file = tmp_path / "target_module.py"
    target_file.write_text("def target_func():\n    return 0\n", encoding="utf-8")

    mock_result = AIGovernanceResult(
        is_fixable=True,
        reasoning="Test fix: return 1 instead of 0",
        root_cause="Incorrect return value",
        patch_proposal=PatchProposal(
            target_function="target_func",
            suggested_code="return 1",
            patch_type=PatchType.REFACTORING,  # REFACTORING 触发 requires_approval=True
            required_imports=[],
        ),
        confidence_score=0.6,
        source="llm",
    )

    mock_git = MagicMock()
    patches = [
        patch.object(orchestrator.agent, "analyze_with_context",
                     AsyncMock(return_value=mock_result)),
        patch.object(orchestrator, "_resolve_file_path",
                     return_value=str(target_file)),
        patch.object(orchestrator.executor._path_validator, "validate_path",
                     return_value=(True, "test mode: path validation bypassed for E2E")),
        patch.object(orchestrator, "git_mgr", mock_git),
    ]
    for p in patches:
        p.start()

    yield {"target_file": str(target_file), "mock_result": mock_result}

    for p in patches:
        p.stop()


class TestE2EWorkflowGovernanceFlow:
    """端到端测试：工作流 → 治理 → 审批完整流程"""

    def test_full_workflow_governance_approval_flow(
        self, client, admin_headers, governance_mock_setup
    ):
        """正向: 工作流创建 → 执行 → 治理诊断 → 审批通过 → 补丁应用 → 追踪验证。

        旧版假绿根因 (三层):
          1. /governance/execute 不传 actual_output/expected_baseline →
             _classify_exception 返回 MANUAL_REQUIRED → SKIPPED → 无审批记录创建
          2. if approvals_data["data"]["count"] > 0 守卫 → 无审批时静默跳过全部断言
          3. 用 approvals[0]["tx_id"] 取 stale 审批 (其他测试遗留) → 补丁目标文件不存在 → 失败

        严格修复:
          - 传 actual_output != expected_baseline 触发 AI_DIAGNOSE 分类
          - 用响应中的 tx_id (非 approvals[0])
          - 删除 if count > 0 弱守卫, 强制断言审批存在且可应用
          - 验证补丁真实应用 (临时文件内容从 return 0 变为 return 1)
        """
        # === 工作流部分 (保持不变, 验证工作流基础能力) ===
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
<<<<<<< Updated upstream
        status_data = response.json()
        status = status_data.get("data", status_data)
        assert status["instance_id"] == instance_id
        assert status["workflow_id"] == workflow_id
=======
        status_resp = response.json()
        status_data = status_resp.get("data", status_resp)
        assert status_data["instance_id"] == instance_id
        assert status_data["workflow_id"] == workflow_id
>>>>>>> Stashed changes

        # === 治理部分 (严格修复) ===
        # 传 actual_output != expected_baseline 触发 AI_DIAGNOSE (orchestrator.py:277-278)
        step_id = f"gov_{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "test_component",
                "step_id": step_id,
                "actual_output": "wrong",
                "expected_baseline": "right",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        governance_data = response.json()
        assert governance_data["success"] is True
        assert "trace_id" in governance_data["data"]
        # REFACTORING 补丁必须触发审批 (approval.py:33-43)
        assert governance_data["data"]["status"] == "PENDING_APPROVAL", (
            f"REFACTORING 补丁应需审批, 实际 status={governance_data['data']['status']}"
        )
        tx_id = governance_data["data"]["tx_id"]
        assert tx_id is not None, "PENDING_APPROVAL 必须返回 tx_id"

        # 审批通过 → 补丁应用 → FIXED
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 200
        approval_result = response.json()
        assert approval_result["success"] is True, (
            f"审批应成功, 实际: {approval_result}"
        )
        assert approval_result["data"]["tx_id"] == tx_id
        assert approval_result["data"]["status"] == "FIXED", (
            f"补丁应用后应为 FIXED, 实际: {approval_result['data']['status']}"
        )

        # 严格验证: 补丁真实应用 (临时文件内容变更)
        target_file = Path(governance_mock_setup["target_file"])
        patched_content = target_file.read_text(encoding="utf-8")
        assert "return 1" in patched_content, (
            f"补丁未真实应用, 文件内容: {patched_content}"
        )
        assert "return 0" not in patched_content, (
            f"旧代码仍存在, 文件内容: {patched_content}"
        )

        # 验证追踪记录
        response = client.get("/governance/tracker/events", headers=admin_headers)
        assert response.status_code == 200
        tracker_data = response.json()
        assert tracker_data["success"] is True
        assert len(tracker_data["data"]["events"]) > 0

    def test_workflow_execution_idempotency(self, client, admin_headers):
        """同一工作流存在 RUNNING 实例时, 再次执行必须被拒绝 (workflow.py:333-336 幂等检查)。

<<<<<<< Updated upstream
        验证点：
        1. 同一工作流不应有多个RUNNING实例
        2. 重复执行应返回错误提示

        说明：execute_workflow 当前为同步执行，单线程 TestClient 环境下无法产生
        真正的并发调用。因此先执行一次工作流（同步完成），再手动将实例状态标记
        为 RUNNING 以模拟"工作流正在执行中"的并发前置条件，然后验证幂等性守卫
        正确拦截第二次执行请求。此测试验证的是 WorkflowEngine 中的 RUNNING 状态
        检查逻辑，而非 HTTP 层的并发调度。
        """
        from src.platform.api import workflow_engine
        from src.platform.workflow import WorkflowStatus
=======
        旧版假绿根因: 假设第一次 execute 后实例仍 RUNNING → 第二次 execute 返回 "already running"。
        实际: execute_workflow 同步 await 任务 (workflow.py:366), 简单监控任务瞬间完成 →
              第二次 execute 时实例已 COMPLETED, 幂等检查不触发 → 返回 success=True →
              `assert not result["success"]` 失败。旧版因集成测试被 skip 而长期隐藏。

        严格修复: 直接预置一个 RUNNING 实例 (模拟并发/长任务场景), 验证幂等检查逻辑本身,
        而非依赖异步时序。预置实例与 API 端点共享同一 workflow_engine 单例 (api.workflow_engine)。
        """
        from src.platform.api import workflow_engine
        from src.platform.workflow import WorkflowInstance, WorkflowStatus
        from datetime import datetime
>>>>>>> Stashed changes

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

<<<<<<< Updated upstream
        # 第一次执行（同步完成）
        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        first_result = response.json()
        assert first_result["success"] is True
        instance_id = first_result["data"]["instance_id"]

        # 手动将实例状态标记为 RUNNING，模拟工作流正在执行中的并发场景
        with workflow_engine._lock:
            workflow_engine.instances[instance_id].status = WorkflowStatus.RUNNING

        # 再次执行应被幂等性守卫拦截
=======
        # 预置一个 RUNNING 实例 (模拟长任务未完成 / 并发执行场景)
        # workflow_engine 是 api 模块级单例, 端点 execute_workflow 与此处共享同一实例
        running_instance_id = "pre-seeded-running-" + uuid.uuid4().hex[:6]
        with workflow_engine._lock:
            workflow_engine.instances[running_instance_id] = WorkflowInstance(
                workflow_id=workflow_id,
                instance_id=running_instance_id,
                status=WorkflowStatus.RUNNING,
                started_at=datetime.now(),
            )

        # 再次执行 → 幂等检查应发现 RUNNING 实例并拒绝 (workflow.py:335-336)
>>>>>>> Stashed changes
        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        result = response.json()
        assert not result["success"], (
            f"存在 RUNNING 实例时应拒绝执行, 实际 success={result['success']}, "
            f"message={result.get('message')!r}"
        )
        assert "already running" in result.get("message", "").lower(), (
            f"应返回 'already running', 实际 message={result.get('message')!r}"
        )


class TestE2EGovernanceApprovalFlow:
    """端到端测试：治理审批完整流程"""

    def test_approval_expire_handling(
        self, client, admin_headers, governance_mock_setup
    ):
        """边界: 审批记录过期后不能被批准 (api.py:753 is_expired 检查)。

        旧版假绿根因:
          1. /governance/execute 不传 actual_output/expected_baseline → SKIPPED → 无审批
          2. if count > 0 + if record 守卫 → 无审批时静默跳过全部断言 → 假绿
          3. 旧版断言 status_code == 200 → 实际 API 返回 400 (HTTPException) → 断言永远不执行

        严格修复:
          - 传 actual_output != expected_baseline 触发 AI_DIAGNOSE
          - 用响应中的 tx_id (非 approvals[0])
          - 删除 if count > 0 / if record 弱守卫
          - 断言 400 (HTTPException 被 http_exception_handler 转为 ErrorResponse)
        """
        from src.platform.api import approval_manager
        from datetime import datetime, timedelta

        step_id = f"expire_{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "expire_test",
                "step_id": step_id,
                "actual_output": "wrong",
                "expected_baseline": "right",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        gov_data = response.json()
        assert gov_data["data"]["status"] == "PENDING_APPROVAL", (
            f"REFACTORING 补丁应需审批, 实际 status={gov_data['data']['status']}"
        )
        tx_id = gov_data["data"]["tx_id"]

        # 使审批过期 (直接修改全局 approval_manager 单例中的记录)
        record = approval_manager.get_approval(tx_id)
        assert record is not None, f"审批记录应存在: {tx_id}"
        record.expires_at = datetime.now() - timedelta(minutes=1)
        assert record.is_expired, "过期时间设置后 is_expired 应为 True"

        # 过期审批应被拒绝: API 返回 400 (api.py:753-754)
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 400, (
            f"过期审批应返回 400, 实际: {response.status_code}, body: {response.text}"
        )
        result = response.json()
        assert result["success"] is False
        assert "过期" in result["message"], (
            f"应提示'过期', 实际 message: {result['message']}"
        )

    def test_approval_idempotency(
        self, client, admin_headers, governance_mock_setup
    ):
        """边界: 已批准的审批不能再次批准 (api.py:755 status != PENDING 检查)。

        旧版假绿根因:
          1. /governance/execute 不传 actual_output/expected_baseline → SKIPPED → 无审批
          2. if count > 0 守卫 → 无审批时静默跳过全部断言
          3. 旧版第二次 approve 断言 status_code == 200 → 实际 API 返回 400
          4. 用 approvals[0] 可能取到 stale 审批

        严格修复:
          - 传 actual_output != expected_baseline 触发 AI_DIAGNOSE
          - 用响应中的 tx_id
          - 第一次 approve: 200 + success=True + FIXED
          - 第二次 approve: 400 + success=False (状态非 PENDING)
        """
        step_id = f"idem_{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "idem_test",
                "step_id": step_id,
                "actual_output": "wrong",
                "expected_baseline": "right",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        gov_data = response.json()
        assert gov_data["data"]["status"] == "PENDING_APPROVAL"
        tx_id = gov_data["data"]["tx_id"]

        # 第一次审批 → 成功 (补丁应用 → FIXED)
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 200
        first_result = response.json()
        assert first_result["success"] is True, (
            f"第一次审批应成功, 实际: {first_result}"
        )
        assert first_result["data"]["status"] == "FIXED"

        # 第二次审批 → 拒绝 (api.py:755: status != PENDING → 400)
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 400, (
            f"重复审批应返回 400, 实际: {response.status_code}, body: {response.text}"
        )
        second_result = response.json()
        assert second_result["success"] is False
        assert "状态" in second_result["message"], (
            f"应提示状态错误, 实际 message: {second_result['message']}"
        )


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

<<<<<<< Updated upstream
        # 删除成员端点路径参数为 user_id（"1"），而非 username（"admin"）
        response = client.delete(f"/teams/{team_id}/members/1", headers=admin_headers)
=======
        # DELETE 路由参数是 {user_id} (api.py:1288), 不是 username。
        # 成员以 user_id="1" 添加 (上一行 json), 故删除用 members/1 而非 members/admin。
        # 旧版用 members/admin → remove_member(team_id, "admin") 找不到 user_id="admin" → 404。
        response = client.delete(f"/teams/{team_id}/members/1", headers=admin_headers)
        assert response.status_code == 200, (
            f"删除成员应 200 (user_id=1), 实际: {response.status_code}, body: {response.text}"
        )

        # 严格验证: 删除后成员列表不再包含 admin
        response = client.get(f"/teams/{team_id}/members", headers=admin_headers)
>>>>>>> Stashed changes
        assert response.status_code == 200
        remaining = response.json()["data"]["members"]
        assert not any(m["username"] == "admin" for m in remaining), (
            f"删除后成员列表不应包含 admin, 实际: {remaining}"
        )

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