import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.governance.orchestrator import governance_transaction, GovernanceOrchestrator
from src.governance.models import DiagnosticContext, PatchProposal, GovernanceAction, PatchType
from src.governance.approval import ApprovalStatus


class TestGovernanceTransaction:
    """治理事务上下文管理器测试"""

    def test_transaction_success(self):
        git_mgr = MagicMock()
        tx_id = "test_tx"
        proposal = MagicMock()
        proposal.target_function = "test_func"

        with governance_transaction(git_mgr, tx_id, proposal):
            pass

        git_mgr.start_transaction.assert_called_once_with(tx_id)
        git_mgr.commit.assert_called_once()

    def test_transaction_failure(self):
        git_mgr = MagicMock()
        tx_id = "test_tx"
        proposal = MagicMock()
        proposal.target_function = "test_func"

        with pytest.raises(RuntimeError, match="test error"):
            with governance_transaction(git_mgr, tx_id, proposal):
                raise RuntimeError("test error")

        git_mgr.start_transaction.assert_called_once_with(tx_id)
        git_mgr.rollback.assert_called_once_with(tx_id)


class TestGovernanceOrchestrator:
    """治理编排器测试"""

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

    @pytest.mark.asyncio
    async def test_execute_governance_flow_non_governable(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        with patch.object(self.orchestrator, '_classify_exception', return_value=GovernanceAction.ABORT):
            result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "SKIPPED"
        assert result["reason"] == "Non-governable"
        self.orchestrator.tracker.record_event.assert_called()

    @pytest.mark.asyncio
    async def test_execute_governance_flow_not_fixable(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = False
        diagnosis.patch_proposal = None
        diagnosis.confidence_score = 0.5
        diagnosis.reasoning = "Not fixable"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "SKIPPED"
        assert result["reason"] == "Not fixable"

    @pytest.mark.asyncio
    async def test_execute_governance_flow_approval_required(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        patch_proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = patch_proposal
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "Needs fix"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis
        self.orchestrator.approval_mgr.requires_approval.return_value = True

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "PENDING_APPROVAL"
        assert result["approval_required"] is True
        assert "tx_id" in result

    @pytest.mark.asyncio
    async def test_execute_governance_flow_patch_applied_success(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        patch_proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = patch_proposal
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "Can fix"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch.return_value = True

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        self.orchestrator.executor.apply_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_governance_flow_executor_failure(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        patch_proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = patch_proposal
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "Can fix"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch.return_value = False

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_execute_governance_flow_exception(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        patch_proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = patch_proposal
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "Can fix"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch.side_effect = Exception("Apply failed")

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FAILED"
        assert "reason" in result

    def test_classify_exception(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        result = self.orchestrator._classify_exception(context)
        assert result == GovernanceAction.AI_DIAGNOSE

    def test_resolve_file_path_with_mapping(self):
        result = self.orchestrator._resolve_file_path("EvalPlatformProcessor")
        assert result == "extensions/eval_platform/processor.py"

    def test_resolve_file_path_default(self):
        result = self.orchestrator._resolve_file_path("UnknownComponent")
        assert result == "src/components/UnknownComponent.py"

    @pytest.mark.asyncio
    async def test_approve_and_apply_record_not_found(self):
        self.orchestrator.approval_mgr.get_approval.return_value = None

        result = await self.orchestrator.approve_and_apply("nonexistent_tx", "admin")

        assert result["status"] == "FAILED"
        assert result["reason"] == "Approval record not found"

    @pytest.mark.asyncio
    async def test_approve_and_apply_approval_failed(self):
        record = MagicMock()
        record.context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record.proposal = MagicMock()
        record.proposal.patch_type = PatchType.SECURITY

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = False

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FAILED"
        assert result["reason"] == "Approval failed"

    @pytest.mark.asyncio
    async def test_approve_and_apply_success(self):
        record = MagicMock()
        record.context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record.proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = True
        self.orchestrator.executor.apply_patch.return_value = True

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FIXED"
        assert result["approved_by"] == "admin"

    @pytest.mark.asyncio
    async def test_approve_and_apply_executor_failure(self):
        record = MagicMock()
        record.context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record.proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = True
        self.orchestrator.executor.apply_patch.return_value = False

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_approve_and_apply_exception(self):
        record = MagicMock()
        record.context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record.proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = True
        self.orchestrator.executor.apply_patch.side_effect = Exception("Apply failed")

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FAILED"
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_execute_governance_flow_with_class_method(self):
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        patch_proposal = PatchProposal(
            target_function="MyClass.my_method",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        diagnosis = MagicMock()
        diagnosis.is_fixable = True
        diagnosis.patch_proposal = patch_proposal
        diagnosis.confidence_score = 0.9
        diagnosis.reasoning = "Can fix"

        self.orchestrator.agent.analyze_with_context.return_value = diagnosis
        self.orchestrator.approval_mgr.requires_approval.return_value = False
        self.orchestrator.executor.apply_patch.return_value = True

        result = await self.orchestrator.execute_governance_flow(context)

        assert result["status"] == "FIXED"
        self.orchestrator.executor.apply_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_and_apply_with_class_method(self):
        record = MagicMock()
        record.context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record.proposal = PatchProposal(
            target_function="MyClass.my_method",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = True
        self.orchestrator.executor.apply_patch.return_value = True

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FIXED"
