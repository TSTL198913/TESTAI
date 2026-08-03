"""BUG-014: GovernanceOrchestrator 审批流程完整性测试。

源码位置:src/governance/orchestrator.py:37-200 GovernanceOrchestrator

测试场景:
1. 完整治理流程：诊断→创建审批→审批→应用补丁
2. 需要审批的补丁在未审批前不应被应用
3. 审批拒绝后不应应用补丁
4. 流程状态追踪完整性

正确行为:
- 需要审批的补丁状态应为 PENDING_APPROVAL
- 审批后状态应变为 FIXED 或 REJECTED
- 拒绝后不应执行补丁应用
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.models import DiagnosticContext, PatchProposal, GovernanceAction, PatchType
from src.governance.approval import ApprovalStatus


class TestOrchestratorApprovalFlow:
    """GovernanceOrchestrator审批流程测试"""

    @pytest.fixture
    def isolated_orchestrator(self):
        """创建隔离的orchestrator实例"""
        with patch('src.governance.orchestrator.ApprovalManager') as mock_approval:
            mock_instance = MagicMock()
            mock_approval.return_value = mock_instance
            with patch('src.governance.orchestrator.GovernanceExecutor') as mock_executor:
                exec_instance = MagicMock()
                exec_instance.apply_patch = AsyncMock(return_value=True)
                mock_executor.return_value = exec_instance
                with patch('src.governance.orchestrator.GitTransactionManager') as mock_git:
                    git_instance = MagicMock()
                    mock_git.return_value = git_instance
                    with patch('src.governance.orchestrator.GovernanceTracker') as mock_tracker:
                        tracker_instance = MagicMock()
                        mock_tracker.return_value = tracker_instance
                        with patch('src.governance.orchestrator.AIGovernanceAgent') as mock_agent:
                            agent_instance = MagicMock()
                            agent_instance.analyze_with_context = AsyncMock(
                                return_value=MagicMock(
                                    is_fixable=True,
                                    reasoning="Test fix",
                                    confidence_score=0.9,
                                    source="llm",
                                    patch_proposal=PatchProposal(
                                        target_function="test_func",
                                        suggested_code="pass",
                                        patch_type=PatchType.SECURITY,
                                    ),
                                )
                            )
                            mock_agent.return_value = agent_instance
                            yield GovernanceOrchestrator()

    @pytest.mark.asyncio
    async def test_approval_required_flow(self, isolated_orchestrator):
        """边界：需要审批的补丁应返回PENDING_APPROVAL状态"""
        orchestrator = isolated_orchestrator
        orchestrator.approval_mgr.requires_approval.return_value = True
        orchestrator.approval_mgr.create_approval.return_value = None
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="AttributeError: test",
        )
        
        result = await orchestrator.execute_governance_flow(context)
        
        assert result["status"] == "PENDING_APPROVAL", (
            f"需要审批的补丁应返回PENDING_APPROVAL,实际: {result['status']}"
        )
        assert result.get("approval_required") is True
        assert "tx_id" in result
        
        orchestrator.approval_mgr.create_approval.assert_called_once()
        orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_approval_required_flow(self, isolated_orchestrator):
        """正向：不需要审批的补丁应直接应用"""
        orchestrator = isolated_orchestrator
        orchestrator.approval_mgr.requires_approval.return_value = False
        orchestrator.approval_mgr.create_approval.return_value = None
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="AttributeError: test",
        )
        
        result = await orchestrator.execute_governance_flow(context)
        
        assert result["status"] == "FIXED", (
            f"不需要审批且执行成功的补丁应返回FIXED,实际: {result['status']}"
        )
        
        orchestrator.executor.apply_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_fixable_returns_skipped(self, isolated_orchestrator):
        """负向：不可修复的问题应返回SKIPPED"""
        orchestrator = isolated_orchestrator
        orchestrator.agent.analyze_with_context = AsyncMock(
            return_value=MagicMock(
                is_fixable=False,
                reasoning="Not fixable",
                confidence_score=0.5,
                patch_proposal=None,
            )
        )
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        
        result = await orchestrator.execute_governance_flow(context)
        
        assert result["status"] == "SKIPPED", (
            f"不可修复的问题应返回SKIPPED,实际: {result['status']}"
        )
        assert result.get("suggested_fix") is None
        
        orchestrator.approval_mgr.create_approval.assert_not_called()
        orchestrator.executor.apply_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_failure_returns_failed(self, isolated_orchestrator):
        """异常：执行器失败应返回FAILED状态"""
        orchestrator = isolated_orchestrator
        orchestrator.approval_mgr.requires_approval.return_value = False
        orchestrator.executor.apply_patch = AsyncMock(return_value=False)
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="AttributeError: test",
        )
        
        result = await orchestrator.execute_governance_flow(context)
        
        assert result["status"] == "FAILED", (
            f"执行器失败应返回FAILED,实际: {result['status']}"
        )

    def test_classify_exception_code_exception_returns_ai_diagnose(self, isolated_orchestrator):
        """边界：代码级异常应返回AI_DIAGNOSE"""
        orchestrator = isolated_orchestrator
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="AttributeError: 'NoneType' object has no attribute 'split'",
        )
        
        action = orchestrator._classify_exception(context)
        
        assert action == GovernanceAction.AI_DIAGNOSE, (
            f"代码级异常应返回AI_DIAGNOSE,实际: {action}"
        )

    def test_classify_exception_empty_trace_returns_manual_required(self, isolated_orchestrator):
        """边界：空异常跟踪应返回MANUAL_REQUIRED"""
        orchestrator = isolated_orchestrator
        
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="",
        )
        
        action = orchestrator._classify_exception(context)
        
        assert action == GovernanceAction.MANUAL_REQUIRED, (
            f"空异常跟踪应返回MANUAL_REQUIRED,实际: {action}"
        )
