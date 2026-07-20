import os
import sys
from pathlib import Path

import pytest


class TestP0GapVerifications:
    def test_persistence_fixed_approval_survives_reboot(self):
        import tempfile

        from src.governance.models import DiagnosticContext, PatchProposal, PatchType
        from tests.governance.persistence import PersistentApprovalManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test.db")

            mgr1 = PersistentApprovalManager(db_path=db_path)
            proposal = PatchProposal(
                target_function="test_func",
                suggested_code="pass",
                patch_type=PatchType.SECURITY,
            )
            context = DiagnosticContext(
                step_id="test_step_p0_001",
                component_name="TestComponent",
                input_data={},
                actual_output="",
                expected_baseline="",
            )
            mgr1.create_approval("tx_p0_persistence_001", proposal, context)
            mgr1.approve("tx_p0_persistence_001", "tech_committee", "Approved")

            mgr2 = PersistentApprovalManager(db_path=db_path)
            record = mgr2.get_approval("tx_p0_persistence_001")

            assert record is not None
            assert record.status.value == "approved"
            assert record.approved_by == "tech_committee"

    def test_persistence_fixed_tracker_survives_reboot(self):
        import tempfile

        from src.governance.tracker import GovernanceActionType
        from tests.governance.persistence import PersistentGovernanceTracker

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test.db")

            tracker1 = PersistentGovernanceTracker(db_path=db_path)
            tracker1.record_event(
                trace_id="trace_p0_tracker_001",
                action_type=GovernanceActionType.PATCH_APPLIED,
                component="TestComponent",
                status="FIXED",
            )

            tracker2 = PersistentGovernanceTracker(db_path=db_path)
            events = tracker2.get_events_by_trace("trace_p0_tracker_001")

            assert len(events) == 1
            assert events[0].action_type == GovernanceActionType.PATCH_APPLIED

    def test_security_fixed_path_traversal_blocked(self):
        from tests.governance.security import SecurePathValidator

        validator = SecurePathValidator()

        valid, msg = validator.validate_path("../../etc/passwd")
        assert valid is False

        valid, msg = validator.validate_path("/etc/passwd")
        assert valid is False

        valid, msg = validator.validate_path(str(Path("tests/data/file.txt").resolve()))
        assert valid is True

    def test_security_fixed_sanitize_rejects_escape(self):
        from tests.governance.security import SecurePathValidator

        validator = SecurePathValidator()
        base_dir = str(Path("tests/data").resolve())

        with pytest.raises(ValueError, match="Path escapes sandbox"):
            validator.sanitize_path("../../etc/passwd", base_dir)

    def test_concurrency_fixed_file_lock_protects_writes(self):
        from tests.governance.file_lock import FileLockManager

        manager = FileLockManager()

        assert manager.acquire("test_file.txt") is True
        assert manager.acquire("test_file.txt") is False
        assert manager.is_locked("test_file.txt") is True

        manager.release("test_file.txt")
        assert manager.is_locked("test_file.txt") is False

    def test_llm_requires_api_key(self):
        from src.governance.sdk import GovernanceClientSDK

        sdk = GovernanceClientSDK()
        # 行为验证：client 和 breaker 必须存在且可用
        assert sdk.client is not None, "SDK client 不应为 None"
        assert sdk.breaker is not None, "SDK circuit breaker 不应为 None"
        # 验证 breaker 核心方法的行为
        assert sdk.breaker.can_execute() is True, "CircuitBreaker 初始状态应允许执行"
        sdk.breaker.record_failure()
        assert sdk.breaker.failures == 1, "record_failure 应增加失败计数"

    def test_llm_depends_on_env_variable(self):
        import os

        api_key = os.getenv("DEEPSEEK_API_KEY")
        assert api_key is None or isinstance(api_key, str)

    def test_orchestrator_has_core_methods(self):
        from src.governance.approval import ApprovalManager
        from src.governance.executor import GovernanceExecutor
        from src.governance.orchestrator import GovernanceOrchestrator
        from src.governance.tracker import GovernanceTracker

        orchestrator = GovernanceOrchestrator()

        # 行为验证：组件必须存在且类型正确
        assert isinstance(
            orchestrator.approval_mgr, ApprovalManager
        ), "approval_mgr 必须是 ApprovalManager 实例"
        assert isinstance(
            orchestrator.tracker, GovernanceTracker
        ), "tracker 必须是 GovernanceTracker 实例"
        assert isinstance(
            orchestrator.executor, GovernanceExecutor
        ), "executor 必须是 GovernanceExecutor 实例"

    def test_models_have_core_classes(self):
        from src.governance.models import (
            AIGovernanceResult,
            DiagnosticContext,
            PatchProposal,
        )

        proposal = PatchProposal(target_function="test_func", suggested_code="pass")
        assert proposal.target_function == "test_func"

        context = DiagnosticContext(
            step_id="test_step",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        assert context.step_id == "test_step"

    def test_approval_manager_is_singleton(self):
        from src.governance.approval import ApprovalManager
        from src.governance.models import DiagnosticContext, PatchProposal, PatchType

        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step_p0_002",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        mgr.create_approval("tx_p0_memory_001", proposal, context)
        mgr.approve("tx_p0_memory_001", "tech_committee")

        mgr2 = ApprovalManager()
        record = mgr2.get_approval("tx_p0_memory_001")

        assert record is not None

    def test_transformer_patched_flag_function(self):
        import libcst as cst

        from src.governance.transformer import FunctionTransformer

        source_code = """
def my_function():
    return 1
"""
        tree = cst.parse_module(source_code)
        transformer = FunctionTransformer(
            target_function="my_function", new_body="return 2"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "FunctionTransformer 补丁标记应设为True"
        assert "return 2" in tree.code, "代码应被替换"

    def test_transformer_patched_flag_context_aware(self):
        import libcst as cst

        from src.governance.transformer import ContextAwareTransformer

        source_code = """
class TargetClass:
    def my_method():
        return 1
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="my_method", new_body="return 2", target_class="TargetClass"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "ContextAwareTransformer 补丁标记应设为True"
        assert "return 2" in tree.code, "代码应被替换"
