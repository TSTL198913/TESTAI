import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.governance.orchestrator import governance_transaction, GovernanceOrchestrator
from src.governance.models import DiagnosticContext, PatchProposal, GovernanceAction, PatchType
from src.governance.tracker import GovernanceActionType
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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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

        # Mock decision engine to return REQUIRE_MANUAL so the approval flow
        # is triggered (real engine would AUTO_APPROVE at confidence=0.9 + SECURITY)
        self.orchestrator.decision_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "REQUIRE_MANUAL"
        mock_decision.reason = "Manual approval required for security patch"
        self.orchestrator.decision_engine.evaluate.return_value = mock_decision

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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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

    @pytest.mark.asyncio
    async def test_execute_governance_flow_agent_exception_records_failed_event(self):
        """P1-1/P1-2: Agent 异常时审计链必须完整,记录 DIAGNOSE_COMPLETE FAILED 事件。

        验证点:
        1. agent.analyze_with_context 抛异常时不向上传播,而是返回 FAILED
        2. tracker.record_event 必须记录 DIAGNOSE_COMPLETE + status=FAILED
        3. 返回结果包含 status=FAILED 和具体错误信息
        """
        context = DiagnosticContext(
            step_id="step_agent_fail",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="ValueError: bad input",
        )

        # Agent 抛出异常
        self.orchestrator.agent.analyze_with_context.side_effect = RuntimeError("LLM API timeout")

        result = await self.orchestrator.execute_governance_flow(context)

        # 1. 返回 FAILED 状态
        assert result["status"] == "FAILED", (
            f"Agent 异常时应返回 FAILED, 实际: {result['status']}"
        )
        assert "error" in result, "FAILED 结果必须包含 error 字段"
        assert "LLM API timeout" in result["error"], (
            f"error 字段必须包含原始异常信息, 实际: {result.get('error')}"
        )
        assert result["confidence_score"] == 0.0, "异常时置信度必须为 0"

        # 2. 验证审计链:必须记录 DIAGNOSE_COMPLETE + status=FAILED
        record_event_calls = self.orchestrator.tracker.record_event.call_args_list
        diagnose_complete_calls = [
            call for call in record_event_calls
            if call.kwargs.get("action_type") == GovernanceActionType.DIAGNOSE_COMPLETE
        ]
        assert len(diagnose_complete_calls) >= 1, (
            "Agent 异常时必须记录 DIAGNOSE_COMPLETE 事件以补全审计链"
        )
        failed_calls = [
            call for call in diagnose_complete_calls
            if call.kwargs.get("status") == "FAILED"
        ]
        assert len(failed_calls) >= 1, (
            "DIAGNOSE_COMPLETE 事件必须标记 status=FAILED"
        )
        # 验证事件中包含异常信息
        failed_call = failed_calls[0]
        assert failed_call.kwargs.get("message") is not None, (
            "FAILED 事件必须包含异常信息 message"
        )
        assert "LLM API timeout" in failed_call.kwargs.get("message"), (
            f"FAILED 事件 message 必须包含异常信息, 实际: {failed_call.kwargs.get('message')}"
        )

    @pytest.mark.asyncio
    async def test_execute_governance_flow_agent_exception_does_not_break_flow(self):
        """P1-1: Agent 异常不应导致整个流程崩溃(不向上抛出)。"""
        context = DiagnosticContext(
            step_id="step_no_crash",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="KeyError: 'missing'",
        )

        self.orchestrator.agent.analyze_with_context.side_effect = ValueError("Critical LLM failure")

        # 不应抛出异常
        result = await self.orchestrator.execute_governance_flow(context)
        assert result["status"] == "FAILED"
        assert "Critical LLM failure" in result["error"]

    def test_classify_exception_network_error_returns_retry(self):
        """P1-3: 网络异常应分类为 RETRY。"""
        network_traces = [
            "ConnectionError: Failed to establish connection",
            "TimeoutError: Request timed out after 30s",
            "ConnectionResetError: Connection reset by peer",
            "ConnectionRefusedError: Connection refused",
            "OSError: Network unreachable",
        ]
        for trace in network_traces:
            context = DiagnosticContext(
                step_id="step_net",
                component_name="test",
                input_data={},
                actual_output="",
                expected_baseline="",
                exception_trace=trace,
            )
            result = self.orchestrator._classify_exception(context)
            assert result == GovernanceAction.RETRY, (
                f"网络异常应分类为 RETRY, trace={trace!r}, 实际: {result}"
            )

    def test_classify_exception_code_error_returns_ai_diagnose(self):
        """P1-3: 代码级异常应分类为 AI_DIAGNOSE。"""
        code_traces = [
            "SyntaxError: invalid syntax",
            "NameError: name 'foo' is not defined",
            "TypeError: unsupported operand type",
            "ValueError: invalid literal for int()",
            "AttributeError: 'NoneType' object has no attribute 'x'",
            "KeyError: 'missing_key'",
            "IndexError: list index out of range",
            "ZeroDivisionError: division by zero",
        ]
        for trace in code_traces:
            context = DiagnosticContext(
                step_id="step_code",
                component_name="test",
                input_data={},
                actual_output="",
                expected_baseline="",
                exception_trace=trace,
            )
            result = self.orchestrator._classify_exception(context)
            assert result == GovernanceAction.AI_DIAGNOSE, (
                f"代码级异常应分类为 AI_DIAGNOSE, trace={trace!r}, 实际: {result}"
            )

    def test_classify_exception_unknown_returns_manual_required(self):
        """P1-3: 未知异常应分类为 MANUAL_REQUIRED。"""
        unknown_traces = [
            "SomeWeirdUnknownError: something happened",
            "RuntimeError: generic runtime issue",
            "SystemExit: 1",
        ]
        for trace in unknown_traces:
            context = DiagnosticContext(
                step_id="step_unknown",
                component_name="test",
                input_data={},
                actual_output="",
                expected_baseline="",
                exception_trace=trace,
            )
            result = self.orchestrator._classify_exception(context)
            assert result == GovernanceAction.MANUAL_REQUIRED, (
                f"未知异常应分类为 MANUAL_REQUIRED, trace={trace!r}, 实际: {result}"
            )

    def test_classify_exception_empty_trace_returns_manual_required(self):
        """P1-3: 空 exception_trace 应分类为 MANUAL_REQUIRED。"""
        context = DiagnosticContext(
            step_id="step_empty",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace=None,
        )
        result = self.orchestrator._classify_exception(context)
        assert result == GovernanceAction.MANUAL_REQUIRED, (
            f"空 exception_trace 应分类为 MANUAL_REQUIRED, 实际: {result}"
        )

    def test_classify_exception_case_insensitive(self):
        """P1-3: 异常分类应大小写不敏感(小写 trace 也能识别)。"""
        context = DiagnosticContext(
            step_id="step_lower",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="connectionerror: failed to connect",
        )
        result = self.orchestrator._classify_exception(context)
        assert result == GovernanceAction.RETRY, (
            f"小写 connectionerror 应识别为 RETRY, 实际: {result}"
        )

    def test_classify_exception_baseline_mismatch_returns_ai_diagnose(self):
        """P1-3 回归防护:无异常 trace 但存在基线偏差时应触发 AI 诊断。

        场景:测试执行未抛异常,但实际输出与预期基线不一致,
        此时应交由 AI 诊断根因,而非返回 MANUAL_REQUIRED 导致流程被跳过。
        """
        context = DiagnosticContext(
            step_id="step_baseline_mismatch",
            component_name="test",
            input_data={},
            actual_output="error response",
            expected_baseline="success response",
            exception_trace="",
        )
        result = self.orchestrator._classify_exception(context)
        assert result == GovernanceAction.AI_DIAGNOSE, (
            f"基线偏差(actual != expected)应触发 AI_DIAGNOSE, 实际: {result}"
        )

    def test_classify_exception_no_trace_no_mismatch_returns_manual_required(self):
        """P1-3: 既无异常 trace 也无基线偏差时返回 MANUAL_REQUIRED。"""
        context = DiagnosticContext(
            step_id="step_empty",
            component_name="test",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="",
        )
        result = self.orchestrator._classify_exception(context)
        assert result == GovernanceAction.MANUAL_REQUIRED, (
            f"既无 trace 也无基线偏差应返回 MANUAL_REQUIRED, 实际: {result}"
        )

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
            exception_trace="ValueError: test error",
        )
        record.proposal = MagicMock()
        record.proposal.patch_type = PatchType.SECURITY
        record.status = ApprovalStatus.PENDING

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
            exception_trace="ValueError: test error",
        )
        record.proposal = PatchProposal(
            target_function="test_func",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )
        record.status = ApprovalStatus.PENDING

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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
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
            exception_trace="ValueError: test error",
        )
        record.proposal = PatchProposal(
            target_function="MyClass.my_method",
            suggested_code='return "fixed"',
            patch_type=PatchType.SECURITY,
        )
        record.status = ApprovalStatus.PENDING

        self.orchestrator.approval_mgr.get_approval.return_value = record
        self.orchestrator.approval_mgr.approve.return_value = True
        self.orchestrator.executor.apply_patch.return_value = True

        result = await self.orchestrator.approve_and_apply("tx1", "admin")

        assert result["status"] == "FIXED"
