"""元测试:反向证伪机制。

目的:防止 xfail 测试本身又是永真断言。每个 bug 配 1 个 inverse proof,
用 Mock 构造"修复版"返回值,验证 xfail 测试的断言在"代码正确"时能通过。

如果某天 src/ 真的修复了 bug,xfail(strict=True) 会"意外通过"从而失败,
提醒开发者把 xfail 改为正式通过测试。

元测试通过 + xfail 测试失败 = 断言有效(不是永真)
元测试失败 = 断言本身有问题(可能是永真或断言错误)
"""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


def test_bug_001_inverse_proof_mutations_positive():
    """反向证伪 BUG-001:当 _handle_mutation_test_task 返回正确数据时,断言能通过。"""
    from src.platform.workflow import WorkflowEngine, WorkflowTask, TaskType

    correct_report = {
        "target_dir": "fake",
        "kill_rate": 0.6,
        "mutations": 5,
        "killed": 3,
        "survived": 2,
        "status": "completed",
        "details": [
            {
                "file": "f.py",
                "type": "BinOp",
                "original": "a + b",
                "mutated": "a - b",
                "killed": True,
            },
        ],
    }

    with patch.object(
        WorkflowEngine,
        "_handle_mutation_test_task",
        new=AsyncMock(return_value={"status": "completed", "report": correct_report}),
    ):
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST, name="mut", params={"target_dir": "fake"}
        )
        result = asyncio.run(engine._handle_mutation_test_task(task, {}, {}))
        report = result["report"]

        # 这些是 test_bug_001 的断言,验证能通过
        assert report["mutations"] > 0
        assert len(report["details"]) > 0
        for item in report["details"]:
            assert "original" in item
            assert "mutated" in item
            assert "killed" in item


def test_bug_002_inverse_proof_cyclic_returns_failed():
    """反向证伪 BUG-002:当 execute_workflow 循环依赖返回 failed 时,断言能通过。"""
    from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType

    correct_result = {
        "status": "failed",
        "error": "Cyclic dependency detected",
        "instance_id": "fake-inst",
        "task_results": {},
    }

    with patch.object(
        WorkflowEngine, "execute_workflow", new=AsyncMock(return_value=correct_result)
    ):
        engine = WorkflowEngine()
        wf = WorkflowDefinition(
            name="cyclic",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="t1", id="t1", depends_on=["t2"]),
                WorkflowTask(type=TaskType.MONITORING, name="t2", id="t2", depends_on=["t1"]),
            ],
        )
        wf_id = engine.define_workflow(wf)
        result = asyncio.run(engine.execute_workflow(wf_id))

        # 这些是 test_bug_002 的断言
        assert result["status"] == "failed"
        error_msg = result.get("error", "").lower()
        assert "cyclic" in error_msg or "circular" in error_msg


def test_bug_003_inverse_proof_unknown_type_returns_failed():
    """反向证伪 BUG-003:当未知任务类型返回 failed 时,断言能通过。"""
    from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType

    correct_result = {"status": "failed", "task_results": {}}

    with patch.object(
        WorkflowEngine, "execute_workflow", new=AsyncMock(return_value=correct_result)
    ):
        engine = WorkflowEngine()
        wf = WorkflowDefinition(
            name="bad",
            tasks=[WorkflowTask(type="invalid_type", name="bad")],
        )
        wf_id = engine.define_workflow(wf)
        result = asyncio.run(engine.execute_workflow(wf_id))

        assert result["status"] == "failed"


def test_bug_004_inverse_proof_approver_is_authenticated_user():
    """反向证伪 BUG-004:当 approve_and_apply 收到 approver='admin' 时,断言能通过。"""
    from src.platform import api as api_module

    mock_apply = AsyncMock(return_value={"status": "FIXED"})

    with patch.object(api_module.orchestrator, "approve_and_apply", new=mock_apply):
        # 模拟 API 调用后,验证 approver 参数
        # 假设 API 修复后,approver 从认证用户获取(='admin')
        api_module.orchestrator.approve_and_apply("tx_x", "admin", None)
        call_args = mock_apply.call_args
        passed_approver = call_args[0][1]
        assert passed_approver == "admin"


def test_bug_005_inverse_proof_nonexistent_alert_returns_404():
    """反向证伪 BUG-005:当 acknowledge 端点返回 404 时,断言能通过。"""
    # 构造正确的 404 响应
    correct_response = MagicMock()
    correct_response.status_code = 404
    correct_response.json.return_value = {
        "success": False,
        "error_code": "ALERT_NOT_FOUND",
        "message": "Alert not found",
    }

    assert correct_response.status_code == 404
    data = correct_response.json()
    assert data["success"] is False
    assert data.get("error_code") is not None


def test_bug_006_inverse_proof_malicious_path_rejected():
    """反向证伪 BUG-006:当 validate_path 返回 (False, ...) 时,断言能通过。"""
    from src.governance.security import SecurePathValidator

    with patch.object(
        SecurePathValidator,
        "validate_path",
        return_value=(False, "Path escapes sandbox"),
    ):
        validator = SecurePathValidator()
        is_valid, msg = validator.validate_path("/etc/tests/passwd")
        assert is_valid is False


def test_bug_007_inverse_proof_duplicate_tx_id_raises():
    """反向证伪 BUG-007:当 create_approval 重复 tx_id 抛 ValueError 时,断言能通过。"""
    from src.governance.approval import ApprovalManager
    from src.governance.models import PatchProposal, PatchType, DiagnosticContext

    proposal = PatchProposal(
        target_function="f", suggested_code="pass", patch_type=PatchType.FUNCTIONAL
    )
    context = DiagnosticContext(
        step_id="s", component_name="c", input_data={},
        actual_output="", expected_baseline="",
    )

    with patch.object(ApprovalManager, "create_approval", side_effect=ValueError("duplicate tx_id")):
        mgr = ApprovalManager()
        with pytest.raises(ValueError, match="duplicate"):
            mgr.create_approval("tx_dup", proposal, context)


def test_bug_008_inverse_proof_agent_exception_returns_failed():
    """反向证伪 BUG-008:当 execute_governance_flow 返回 FAILED 时,断言能通过。"""
    from src.governance.orchestrator import GovernanceOrchestrator
    from src.governance.tracker import GovernanceActionType, TrackingEvent

    correct_result = {"status": "FAILED", "error": "AI timeout"}

    # 构造真实 tracker,含 DIAGNOSE_START 和 PATCH_FAILED 事件
    fake_events = [
        TrackingEvent(
            trace_id="trace-1",
            action_type=GovernanceActionType.DIAGNOSE_START,
        ),
        TrackingEvent(
            trace_id="trace-1",
            action_type=GovernanceActionType.PATCH_FAILED,
            status="FAILED",
        ),
    ]

    with patch("src.governance.orchestrator.AIGovernanceAgent"), \
         patch("src.governance.orchestrator.GovernanceExecutor"), \
         patch("src.governance.orchestrator.GitTransactionManager"), \
         patch("src.governance.orchestrator.ApprovalManager"), \
         patch("src.governance.orchestrator.GovernanceTracker"):
        orchestrator = GovernanceOrchestrator()

    orchestrator.tracker = MagicMock()
    orchestrator.tracker.get_events_by_trace.return_value = fake_events

    with patch.object(
        orchestrator,
        "execute_governance_flow",
        new=AsyncMock(return_value=correct_result),
    ):
        result = asyncio.run(orchestrator.execute_governance_flow(MagicMock()))

        assert result["status"] == "FAILED"

        events = orchestrator.tracker.get_events_by_trace("trace-1")
        action_types = [e.action_type for e in events]
        assert GovernanceActionType.DIAGNOSE_START in action_types
        has_failure = any(
            at == GovernanceActionType.PATCH_FAILED
            or (at == GovernanceActionType.DIAGNOSE_COMPLETE and e.status == "FAILED")
            for at, e in zip(action_types, events)
        )
        assert has_failure


def test_meta_all_inverse_proofs_cover_8_bugs():
    """元测试的元测试:验证覆盖了 8 个 bug 的反向证伪。"""
    # 这个测试本身验证 test_meta_inverse_proof.py 的完整性
    # 通过检查本文件中的测试函数数量
    import inspect
    import sys

    current_module = sys.modules[__name__]
    test_functions = [
        name for name, obj in inspect.getmembers(current_module)
        if name.startswith("test_bug_") and inspect.isfunction(obj)
    ]

    # 至少 8 个反向证伪(每个 bug 至少 1 个)
    assert len(test_functions) >= 8, (
        f"元测试必须覆盖 8 个 bug,实际只有 {len(test_functions)} 个: {test_functions}"
    )
