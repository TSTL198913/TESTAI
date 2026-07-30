import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.governance.approval import ApprovalManager, ApprovalRecord, ApprovalStatus
from src.governance.models import DiagnosticContext, PatchProposal, PatchType


class TestApprovalStatus:
    """审批状态枚举测试"""

    @pytest.mark.parametrize("status,expected_value", [
        (ApprovalStatus.PENDING, "pending"),
        (ApprovalStatus.APPROVED, "approved"),
        (ApprovalStatus.REJECTED, "rejected"),
        (ApprovalStatus.EXPIRED, "expired"),
    ])
    def test_status_enum_values(self, status, expected_value):
        assert status.value == expected_value

    def test_status_count(self):
        assert len(list(ApprovalStatus)) == 4


class TestApprovalRecord:
    """审批记录测试"""

    def test_record_creation(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record = ApprovalRecord("tx_001", proposal, context)

        assert record.tx_id == "tx_001"
        assert record.status == ApprovalStatus.PENDING
        assert record.created_at is not None
        assert not record.is_expired
        assert record.approved_by is None
        assert record.reason is None

    @pytest.mark.parametrize("patch_type,expected", [
        (PatchType.SECURITY, True),
        (PatchType.FUNCTIONAL, False),
        (PatchType.REFACTORING, True),
    ])
    def test_requires_approval(self, patch_type, expected):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=patch_type,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record = ApprovalRecord("tx_001", proposal, context)
        assert record.requires_approval is expected

    def test_record_with_all_fields(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={"key": "value"},
            actual_output="output",
            expected_baseline="expected",
        )
        record = ApprovalRecord("tx_001", proposal, context)
        
        assert record.proposal == proposal
        assert record.context == context
        assert isinstance(record.created_at, datetime)
        assert isinstance(record.expires_at, datetime)

    def test_record_expired(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record = ApprovalRecord("tx_001", proposal, context)
        record.expires_at = datetime.now() - timedelta(minutes=1)
        
        assert record.is_expired is True


class TestApprovalManager:
    """审批管理器测试"""

    def setup_method(self):
        mgr = ApprovalManager()
        mgr._approvals.clear()

    def test_manager_singleton(self):
        mgr1 = ApprovalManager()
        mgr2 = ApprovalManager()
        assert mgr1 is mgr2

    def test_create_approval(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record = mgr.create_approval("tx_create_001", proposal, context)

        assert record is not None
        assert record.tx_id == "tx_create_001"
        assert mgr.get_approval("tx_create_001") is record

    def test_create_duplicate_approval(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        first_record = mgr.create_approval("tx_duplicate", proposal, context)
        
        with pytest.raises(ValueError, match="duplicate"):
            mgr.create_approval("tx_duplicate", proposal, context)

    def test_approve_pending(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_approve_001", proposal, context)

        result = mgr.approve("tx_approve_001", "tech_committee")
        assert result is True

        record = mgr.get_approval("tx_approve_001")
        assert record.status == ApprovalStatus.APPROVED
        assert record.approved_by == "tech_committee"

    def test_reject_pending(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_reject_001", proposal, context)

        result = mgr.reject("tx_reject_001", "tech_committee", "Risky change")
        assert result is True

        record = mgr.get_approval("tx_reject_001")
        assert record.status == ApprovalStatus.REJECTED
        assert record.reason == "Risky change"

    def test_approve_already_approved(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_double_approve", proposal, context)
        mgr.approve("tx_double_approve", "tech_committee")
        
        result = mgr.approve("tx_double_approve", "tech_committee")
        assert result is False

    def test_reject_already_rejected(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_double_reject", proposal, context)
        mgr.reject("tx_double_reject", "tech_committee", "Reason")
        
        result = mgr.reject("tx_double_reject", "tech_committee", "Another reason")
        assert result is False

    def test_approve_nonexistent(self):
        mgr = ApprovalManager()
        result = mgr.approve("tx_nonexistent", "tech_committee")
        assert result is False

    def test_reject_nonexistent(self):
        mgr = ApprovalManager()
        result = mgr.reject("tx_nonexistent", "tech_committee", "No reason")
        assert result is False

    def test_is_approved(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_is_approved_001", proposal, context)

        assert mgr.is_approved("tx_is_approved_001") is False

        mgr.approve("tx_is_approved_001", "tech_committee")
        assert mgr.is_approved("tx_is_approved_001") is True

    def test_is_approved_nonexistent(self):
        mgr = ApprovalManager()
        assert mgr.is_approved("tx_nonexistent") is False

    @pytest.mark.parametrize("patch_type,expected", [
        (PatchType.SECURITY, True),
        (PatchType.FUNCTIONAL, False),
        (PatchType.REFACTORING, True),
    ])
    def test_requires_approval_check(self, patch_type, expected):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=patch_type,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_requires", proposal, context)
        assert mgr.requires_approval("tx_requires") is expected

    def test_requires_approval_nonexistent(self):
        mgr = ApprovalManager()
        assert mgr.requires_approval("tx_nonexistent") is False

    def test_list_pending(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_pending_001", proposal, context)
        mgr.create_approval("tx_pending_002", proposal, context)

        pending = mgr.list_pending()
        assert len(pending) == 2

        mgr.approve("tx_pending_001", "tech_committee")
        pending = mgr.list_pending()
        assert len(pending) == 1

    def test_cleanup_expired(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_cleanup_001", proposal, context)

        record = mgr.get_approval("tx_cleanup_001")
        record.expires_at = record.created_at - timedelta(minutes=1)

        mgr.cleanup_expired()

        record = mgr.get_approval("tx_cleanup_001")
        assert record.status == ApprovalStatus.EXPIRED

    def test_concurrent_approval(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_concurrent", proposal, context)

        results = []
        def approve_task():
            results.append(mgr.approve("tx_concurrent", "tech_committee"))

        threads = [threading.Thread(target=approve_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 1
        record = mgr.get_approval("tx_concurrent")
        assert record.status == ApprovalStatus.APPROVED

    def test_concurrent_reject(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_concurrent_reject", proposal, context)

        results = []
        def reject_task():
            results.append(mgr.reject("tx_concurrent_reject", "tech_committee", "Concurrent"))

        threads = [threading.Thread(target=reject_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 1
        record = mgr.get_approval("tx_concurrent_reject")
        assert record.status == ApprovalStatus.REJECTED

    def test_get_approval_nonexistent(self):
        mgr = ApprovalManager()
        result = mgr.get_approval("tx_nonexistent")
        assert result is None

    def test_list_all_approvals(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_1", proposal, context)
        mgr.create_approval("tx_2", proposal, context)
        
        pending_approvals = mgr.list_pending()
        assert len(pending_approvals) == 2

    def test_create_approval_with_empty_tx_id(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        record = mgr.create_approval("", proposal, context)
        assert record is not None
        assert record.tx_id == ""

    def test_create_approval_with_long_tx_id(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        long_tx_id = "a" * 256
        record = mgr.create_approval(long_tx_id, proposal, context)
        assert record is not None
        assert record.tx_id == long_tx_id

    def test_create_approval_with_special_char_tx_id(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        special_tx_id = "tx_@#$%^&*()_+-=[]{}|;:,.<>?"
        record = mgr.create_approval(special_tx_id, proposal, context)
        assert record is not None
        assert record.tx_id == special_tx_id

    def test_approve_expired(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_expired", proposal, context)
        record = mgr.get_approval("tx_expired")
        record.expires_at = datetime.now() - timedelta(minutes=1)
        
        result = mgr.approve("tx_expired", "tech_committee")
        assert result is False

    def test_reject_expired(self):
        mgr = ApprovalManager()
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
        mgr.create_approval("tx_expired_reject", proposal, context)
        record = mgr._approvals["tx_expired_reject"]
        record.expires_at = datetime.now() - timedelta(minutes=1)
        
        result = mgr.reject("tx_expired_reject", "tech_committee", "Expired")
        assert result is False
        record = mgr._approvals["tx_expired_reject"]
        assert record.status == ApprovalStatus.EXPIRED

    def test_approve_nonexistent_tx_id(self):
        mgr = ApprovalManager()
        result = mgr.approve("tx_nonexistent", "tech_committee")
        assert result is False

    def test_reject_nonexistent_tx_id(self):
        mgr = ApprovalManager()
        result = mgr.reject("tx_nonexistent", "tech_committee", "Reason")
        assert result is False

    def test_cleanup_expired_empty(self):
        mgr = ApprovalManager()
        mgr.cleanup_expired()

    def test_list_pending_empty(self):
        mgr = ApprovalManager()
        pending = mgr.list_pending()
        assert len(pending) == 0
