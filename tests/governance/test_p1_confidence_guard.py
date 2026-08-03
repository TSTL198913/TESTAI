"""P1-1 置信度守卫测试：低置信度补丁不得自动批准，必须走人工审批。

业务规则（基于代码梳理）：
- orchestrator.execute_governance_flow 在 diagnose 后，依据
  approval_mgr.requires_approval(tx_id) 决定是否走人工审批。
- ApprovalRecord.requires_approval 仅检查 patch_type(security/refactoring)
  与 _is_large_change(>=20行)，从不检查 confidence_score。
- 因此低置信度(如 mock 诊断 0.3)的小补丁会被 approve(..., approver="system")
  自动批准并 apply_patch，存在将错误补丁写入生产代码的风险。

修复后规则 (AutoDecisionEngine 接入审批决策):
- AutoDecisionEngine.rule_auto_approve_high_confidence (confidence>=0.9 AND is_fixable
  AND source 不在 mock/fallback) → AUTO_APPROVE → 自动批准 + 执行补丁。
- 其余决策 (REJECT/REQUIRE_MANUAL/ESCALATE/AUTO_ROLLBACK) → PENDING_APPROVAL,
  且不得调用 approve()。
- mock/fallback 降级诊断即使高置信也不自动批准 (P0 source 守卫)。
- 闸门1 ApprovalManager.requires_approval (security/refactoring/行数>=20) 优先级最高,
  覆盖 engine 决策。
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.auto_decision_engine import AutoDecisionEngine
from src.governance.models import DiagnosticContext, PatchProposal, GovernanceAction
from src.governance.registry import PatchType


def _make_context():
    return DiagnosticContext(
        step_id="step_conf",
        component_name="HTTPProcessor",
        input_data={},
        actual_output="actual",
        expected_baseline="expected",
        exception_trace="AttributeError: test error",
    )


def _make_proposal(patch_type=PatchType.FUNCTIONAL, code="def f():\n    return 1\n"):
    return PatchProposal(
        target_function="f",
        suggested_code=code,
        patch_type=patch_type,
        required_imports=[],
    )


class TestConfidenceGuard:
    """置信度守卫：覆盖正向/负向/边界/异常/依赖"""

    def setup_method(self):
        with patch('src.governance.orchestrator.AIGovernanceAgent'):
            with patch('src.governance.orchestrator.GovernanceExecutor'):
                with patch('src.governance.orchestrator.GitTransactionManager'):
                    with patch('src.governance.orchestrator.ApprovalManager'):
                        with patch('src.governance.orchestrator.GovernanceTracker'):
                            self.orchestrator = GovernanceOrchestrator()
        self.orchestrator.agent = AsyncMock()
        self.orchestrator.executor = AsyncMock()
        self.orchestrator.git_mgr = MagicMock()
        self.orchestrator.approval_mgr = MagicMock()
        self.orchestrator.tracker = MagicMock()
        # AutoDecisionEngine 是单例, orchestrator.__init__ 实例化后跨测试累积 history。
        # 清理单例 state 防止跨测试污染 (参考 test_auto_decision_engine.py clean_engine fixture)。
        AutoDecisionEngine()._history.clear()

    @pytest.mark.asyncio
    async def test_low_confidence_forces_manual_approval(self):
        """正向：低置信度(0.3) + requires_approval=False → 必须 PENDING_APPROVAL"""
        context = _make_context()
        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = _make_proposal()
        diagnosis.confidence_score = 0.3
        diagnosis.reasoning = "low confidence"
        diagnosis.source = "llm"
        self.orchestrator.agent.analyze_with_context = AsyncMock(return_value=diagnosis)
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        assert result.get("approval_required") is True
        # 关键断言：低置信度不得自动批准
        self.orchestrator.approval_mgr.approve.assert_not_called()
        # 不得执行补丁
        self.orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_confidence_auto_approved(self):
        """正向：高置信度(0.95) + requires_approval=False → 自动批准 FIXED"""
        context = _make_context()
        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = _make_proposal()
        diagnosis.confidence_score = 0.95
        diagnosis.reasoning = "high confidence"
        diagnosis.source = "llm"
        self.orchestrator.agent.analyze_with_context = AsyncMock(return_value=diagnosis)
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch = AsyncMock(return_value=True)

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        self.orchestrator.approval_mgr.approve.assert_called_once()

    @pytest.mark.asyncio
    async def test_boundary_confidence_just_below_threshold(self):
        """边界：置信度 0.89 (<0.9) → PENDING_APPROVAL"""
        context = _make_context()
        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = _make_proposal()
        diagnosis.confidence_score = 0.89
        diagnosis.reasoning = "borderline"
        diagnosis.source = "llm"
        self.orchestrator.agent.analyze_with_context = AsyncMock(return_value=diagnosis)
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        self.orchestrator.approval_mgr.approve.assert_not_called()

    @pytest.mark.asyncio
    async def test_boundary_confidence_at_threshold_auto_approved(self):
        """边界：置信度恰好 0.9 (=阈值) → 可自动批准 FIXED"""
        context = _make_context()
        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = _make_proposal()
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "at threshold"
        diagnosis.source = "llm"
        self.orchestrator.agent.analyze_with_context = AsyncMock(return_value=diagnosis)
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch = AsyncMock(return_value=True)

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        self.orchestrator.approval_mgr.approve.assert_called_once()

    @pytest.mark.asyncio
    async def test_security_patch_always_manual_even_high_confidence(self):
        """依赖：security patch_type 即使高置信度也 PENDING_APPROVAL"""
        context = _make_context()
        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = _make_proposal(patch_type=PatchType.SECURITY)
        diagnosis.confidence_score = 0.99
        diagnosis.reasoning = "security fix"
        diagnosis.source = "llm"
        self.orchestrator.agent.analyze_with_context = AsyncMock(return_value=diagnosis)
        # security patch_type → requires_approval=True
        self.orchestrator.approval_mgr.requires_approval.return_value = True

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        self.orchestrator.approval_mgr.approve.assert_not_called()
