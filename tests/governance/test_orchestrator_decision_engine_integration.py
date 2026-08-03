"""AutoDecisionEngine 接入 orchestrator 审批决策的集成测试。

测试目标 (规则: 验证业务逻辑正确性, 非单纯覆盖率):
验证 orchestrator._execute_governance_flow_impl 的审批步骤正确接入 AutoDecisionEngine,
两道闸门 (ApprovalManager 结构闸门 + AutoDecisionEngine AI 规则) 互补工作,
且核心 P0 修复生效: mock/fallback 降级诊断即使高置信也不被自动批准。

覆盖五场景 (用户规则: 正向/负向/边界/异常/依赖):
- 正向: 高置信 LLM 自动批准; mock/fallback 降级被拦截
- 负向: 极低置信走人工
- 边界: 0.5 (REJECT 阈值上界) / 0.9 (AUTO_APPROVE 阈值)
- 异常: engine 抛 ValueError/TypeError 安全降级为人工
- 依赖: SECURITY patch_type 被结构闸门拦截 (覆盖 engine 优先级遮蔽)

断言规则: 验证具体业务逻辑 (status + approve/apply_patch 调用次数),
禁止仅验证 status 的弱断言。

已知限制 (诚实声明):
- consecutive_failures 暂传 0, rule_escalate_multiple_failures 不触发 (TODO)。
- patch_category 暂传空, rule_auto_approve_known_pattern 不触发 (TODO)。
- AUTO_ROLLBACK 在审批阶段降级为 PENDING_APPROVAL (无补丁可回滚)。
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.auto_decision_engine import AutoDecisionEngine
from src.governance.models import DiagnosticContext, PatchProposal, GovernanceAction
from src.governance.registry import PatchType


def _make_context():
    return DiagnosticContext(
        step_id="step_integration",
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


def _make_diagnosis(confidence=0.95, is_fixable=True, source="llm",
                    patch_type=PatchType.FUNCTIONAL):
    """构造 mock 诊断结果。source 控制 mock/fallback 守卫测试。"""
    diagnosis = MagicMock()
    diagnosis.is_fixable = is_fixable
    diagnosis.patch_proposal = _make_proposal(patch_type=patch_type)
    diagnosis.confidence_score = confidence
    diagnosis.reasoning = "test reasoning"
    diagnosis.source = source
    return diagnosis


class TestOrchestratorDecisionEngineIntegration:
    """AutoDecisionEngine 接入 orchestrator 审批决策集成测试。"""

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
        # AutoDecisionEngine 单例 state 清理, 防止跨测试 history 污染。
        AutoDecisionEngine()._history.clear()

    # ==================== 正向场景 ====================

    @pytest.mark.asyncio
    async def test_high_confidence_llm_auto_approved(self):
        """正向: 高置信(0.95) + source=llm + FUNCTIONAL + 非结构审批 → FIXED"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.95, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch = AsyncMock(return_value=True)

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        # 业务逻辑断言: 自动批准且执行了补丁
        self.orchestrator.approval_mgr.approve.assert_called_once()
        self.orchestrator.executor.apply_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_mock_high_confidence_blocked(self):
        """正向(核心 P0 修复回归): mock 高置信(0.95) → PENDING_APPROVAL, 不自动批准"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.95, source="mock")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        assert result.get("approval_required") is True
        # 关键断言: mock 降级诊断不得自动批准, 不得执行补丁
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_high_confidence_blocked(self):
        """正向(P0 修复): fallback 高置信(0.95) → PENDING_APPROVAL, 不自动批准"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.95, source="fallback")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        assert result.get("approval_required") is True
        # 关键断言: fallback 降级诊断不得自动批准, 不得执行补丁
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    # ==================== 负向场景 ====================

    @pytest.mark.asyncio
    async def test_very_low_confidence_pending_manual(self):
        """负向: 极低置信(0.3) + source=llm → PENDING_APPROVAL (REJECT 保留人工)"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.3, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        # REJECT 决策映射为 PENDING_APPROVAL (保留人工, 零行为回退), 不批准不执行
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    # ==================== 边界场景 ====================

    @pytest.mark.asyncio
    async def test_boundary_confidence_0_5_pending_manual(self):
        """边界: 置信度 0.5 (=REJECT 阈值上界, 不命中 <0.5) → PENDING_APPROVAL"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.5, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_boundary_confidence_0_9_auto_approved(self):
        """边界: 置信度 0.9 (=AUTO_APPROVE 阈值) + source=llm → FIXED"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.9, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch = AsyncMock(return_value=True)

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        self.orchestrator.approval_mgr.approve.assert_called_once()
        self.orchestrator.executor.apply_patch.assert_called_once()

    # ==================== 依赖场景 ====================

    @pytest.mark.asyncio
    async def test_security_patch_blocked_by_structural_gate(self):
        """依赖: SECURITY + 高置信(0.99) + source=llm → 结构闸门覆盖 → PENDING_APPROVAL

        验证 AutoDecisionEngine 的 rule_security_requires_manual(P80) 被
        rule_auto_approve_high_confidence(P100) 遮蔽时, ApprovalManager 结构闸门兜底。
        """
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(
                confidence=0.99, source="llm", patch_type=PatchType.SECURITY
            )
        )
        # SECURITY patch_type → 结构闸门 requires_approval=True
        self.orchestrator.approval_mgr.requires_approval.return_value = True

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        # 结构闸门覆盖 engine 决策, 即使 engine 可能返回 AUTO_APPROVE 也走人工
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    # ==================== 异常场景 ====================

    @pytest.mark.asyncio
    async def test_engine_value_error_safely_degrades(self):
        """异常: AutoDecisionEngine.evaluate 抛 ValueError → 安全降级 PENDING_APPROVAL"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.95, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        # 替换真实 engine 为抛异常的 mock, 验证安全降级
        self.orchestrator._decision_engine = MagicMock()
        self.orchestrator._decision_engine.evaluate.side_effect = ValueError("boom")

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        # 引擎异常不得自动批准, 不得执行补丁
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_type_error_safely_degrades(self):
        """异常: AutoDecisionEngine.evaluate 抛 TypeError → 安全降级 PENDING_APPROVAL"""
        context = _make_context()
        self.orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=_make_diagnosis(confidence=0.95, source="llm")
        )
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator._decision_engine = MagicMock()
        self.orchestrator._decision_engine.evaluate.side_effect = TypeError("bad type")

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        self.orchestrator.approval_mgr.approve.assert_not_called()
        self.orchestrator.executor.apply_patch.assert_not_called()
