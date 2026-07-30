"""BUG-008: orchestrator agent 异常未捕获 + tracker 审计断链 + _classify_exception 空实现。

源码位置:src/governance/orchestrator.py:46-95 execute_governance_flow

根因:
1. L73 `diagnosis = await self.agent.analyze_with_context(context)` 无 try/except
   —— agent 抛异常时,异常向上抛出到 workflow.py,tracker 只记录了 DIAGNOSE_START,
      无 DIAGNOSE_FAILED 或 PATCH_FAILED,审计链路断链
2. L175-189 的 try/except 只包裹 governance_transaction + executor.apply_patch,不包裹 agent 调用
3. L191-192 _classify_exception 空实现,永远返回 AI_DIAGNOSE,
   所有异常(包括系统级网络错误)都送给 AI 诊断,浪费资源

现有测试反模式:tests/governance/test_orchestrator.py:187-228
- 只测 executor.apply_patch.side_effect = Exception,没测 agent.analyze_with_context 异常
- 全 Mock 屏蔽真实代码,test_classify_exception 只断言返回 AI_DIAGNOSE(把空实现当 expected)
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.models import DiagnosticContext
from src.governance.tracker import GovernanceActionType


def _build_orchestrator_with_real_tracker(tracker):
    """构建 orchestrator,Mock 外部依赖,但保留真实 tracker。"""
    with patch("src.governance.orchestrator.AIGovernanceAgent"), \
         patch("src.governance.orchestrator.GovernanceExecutor"), \
         patch("src.governance.orchestrator.GitTransactionManager"), \
         patch("src.governance.orchestrator.ApprovalManager"):
        orchestrator = GovernanceOrchestrator()
    orchestrator.tracker = tracker
    return orchestrator


@pytest.mark.asyncio
async def test_agent_exception_returns_failed(isolated_tracker, make_context):
    """agent.analyze_with_context 抛异常时,orchestrator 应返回 FAILED,而非向上抛出。

    正确行为:捕获 agent 异常,返回 {"status": "FAILED", ...}。
    当前实现:异常向上抛出,workflow.py 捕获,但 tracker 审计断链。
    """
    orchestrator = _build_orchestrator_with_real_tracker(isolated_tracker)
    orchestrator.agent.analyze_with_context = AsyncMock(
        side_effect=RuntimeError("AI timeout")
    )

    context = make_context(step_id="trace-bug-008", component_name="test",
                          exception_trace="SyntaxError: invalid syntax")

    result = await orchestrator.execute_governance_flow(context)

    assert result["status"] == "FAILED", (
        f"agent 异常时 orchestrator 应返回 FAILED,实际: {result.get('status')}, "
        f"result: {result}"
    )


@pytest.mark.asyncio
async def test_agent_exception_records_failure_event(isolated_tracker, make_context):
    """agent 异常时 tracker 必须记录失败事件,审计链路完整。

    正确行为:tracker 既有 DIAGNOSE_START 也有失败事件(DIAGNOSE_COMPLETE with FAILED 或 PATCH_FAILED)。
    当前实现:只有 DIAGNOSE_START,异常向上抛出,无失败事件。
    """
    orchestrator = _build_orchestrator_with_real_tracker(isolated_tracker)
    orchestrator.agent.analyze_with_context = AsyncMock(
        side_effect=RuntimeError("AI timeout")
    )

    context = make_context(step_id="trace-bug-008-audit", component_name="test",
                          exception_trace="SyntaxError: invalid syntax")

    await orchestrator.execute_governance_flow(context)

    events = isolated_tracker.get_events_by_trace("trace-bug-008-audit")
    action_types = [e.action_type for e in events]

    assert GovernanceActionType.DIAGNOSE_START in action_types, (
        f"必须有 DIAGNOSE_START 事件,实际 action_types: {[at.value for at in action_types]}"
    )

    # 必须有失败事件
    has_failure = any(
        at == GovernanceActionType.PATCH_FAILED
        or (at == GovernanceActionType.DIAGNOSE_COMPLETE and e.status == "FAILED")
        for at, e in zip(action_types, events)
    )
    assert has_failure, (
        f"agent 异常时必须有失败事件(PATCH_FAILED 或 DIAGNOSE_COMPLETE+FAILED), "
        f"实际 action_types: {[at.value for at in action_types]}"
    )


def test_classify_exception_distinguishes_exception_types():
    """_classify_exception 应根据异常类型分类,而非永远返回 AI_DIAGNOSE。

    正确行为:网络异常(如 ConnectionError)应分类为 RETRY 或 MANUAL_REQUIRED,
    代码异常(如 SyntaxError)才送 AI 诊断。
    当前实现:空实现,永远返回 AI_DIAGNOSE,所有异常都送 AI。
    """
    from src.governance.models import GovernanceAction

    with patch("src.governance.orchestrator.AIGovernanceAgent"), \
         patch("src.governance.orchestrator.GovernanceExecutor"), \
         patch("src.governance.orchestrator.GitTransactionManager"), \
         patch("src.governance.orchestrator.ApprovalManager"), \
         patch("src.governance.orchestrator.GovernanceTracker"):
        orchestrator = GovernanceOrchestrator()

    network_ctx = DiagnosticContext(
        step_id="s1",
        component_name="c",
        input_data={},
        actual_output="",
        expected_baseline="",
        exception_trace="ConnectionError: network timeout",
    )
    code_ctx = DiagnosticContext(
        step_id="s2",
        component_name="c",
        input_data={},
        actual_output="",
        expected_baseline="",
        exception_trace="SyntaxError: invalid syntax",
    )

    a_network = orchestrator._classify_exception(network_ctx)
    a_code = orchestrator._classify_exception(code_ctx)

    assert a_network != a_code, (
        f"不同异常类型应分类不同(network={a_network}, code={a_code})。"
        f"当前实现:空实现,两者都返回 AI_DIAGNOSE"
    )


@pytest.mark.asyncio
async def test_agent_exception_result_contains_error_info(isolated_tracker, make_context):
    """agent 异常时 result 必须含 error/reason 字段,便于排查。"""
    orchestrator = _build_orchestrator_with_real_tracker(isolated_tracker)
    orchestrator.agent.analyze_with_context = AsyncMock(
        side_effect=RuntimeError("AI timeout")
    )

    context = make_context(step_id="trace-bug-008-error", component_name="test",
                          exception_trace="SyntaxError: invalid syntax")

    result = await orchestrator.execute_governance_flow(context)

    assert result["status"] == "FAILED"
    assert "error" in result or "reason" in result, (
        f"FAILED 结果必须含 error/reason 字段,实际 result: {result}"
    )
    assert "AI timeout" in str(result.get("error", "")) + str(result.get("reason", "")), (
        f"错误信息应包含原始异常信息,实际 result: {result}"
    )
