from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.governance.approval import (ApprovalManager, ApprovalRecord,
                                     ApprovalStatus)
from src.governance.models import DiagnosticContext, PatchProposal, PatchType


class TestApprovalStatus:
    def test_status_enum_values(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.EXPIRED.value == "expired"


class TestApprovalRecord:
    def test_record_creation(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        record = ApprovalRecord("tx_001", proposal, context)

        assert record.tx_id == "tx_001"
        assert record.status == ApprovalStatus.PENDING
        assert record.created_at is not None
        assert not record.is_expired

    def test_security_patch_requires_approval(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        record = ApprovalRecord("tx_001", proposal, context)
        assert record.requires_approval is True

    def test_functional_patch_no_approval(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        record = ApprovalRecord("tx_001", proposal, context)
        assert record.requires_approval is False

    def test_refactoring_patch_requires_approval(self):
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.REFACTORING
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        record = ApprovalRecord("tx_001", proposal, context)
        assert record.requires_approval is True


class TestApprovalManager:
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
            patch_type=PatchType.FUNCTIONAL
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        record = mgr.create_approval("tx_create_001", proposal, context)

        assert record is not None
        assert record.tx_id == "tx_create_001"
        assert mgr.get_approval("tx_create_001") is record

    def test_approve_pending(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
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
            patch_type=PatchType.SECURITY
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        mgr.create_approval("tx_reject_001", proposal, context)

        result = mgr.reject("tx_reject_001", "tech_committee", "Risky change")
        assert result is True

        record = mgr.get_approval("tx_reject_001")
        assert record.status == ApprovalStatus.REJECTED
        assert record.reason == "Risky change"

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
            patch_type=PatchType.FUNCTIONAL
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        mgr.create_approval("tx_is_approved_001", proposal, context)

        assert mgr.is_approved("tx_is_approved_001") is False

        mgr.approve("tx_is_approved_001", "tech_committee")
        assert mgr.is_approved("tx_is_approved_001") is True

    def test_requires_approval_check(self):
        mgr = ApprovalManager()

        security_proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        mgr.create_approval("tx_requires_001", security_proposal, context)
        assert mgr.requires_approval("tx_requires_001") is True

        functional_proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL
        )
        mgr.create_approval("tx_requires_002", functional_proposal, context)
        assert mgr.requires_approval("tx_requires_002") is False

    def test_list_pending(self):
        mgr = ApprovalManager()
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
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
            patch_type=PatchType.FUNCTIONAL
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline=""
        )
        mgr.create_approval("tx_cleanup_001", proposal, context)

        record = mgr.get_approval("tx_cleanup_001")
        record.expires_at = record.created_at - timedelta(minutes=1)

        mgr.cleanup_expired()

        record = mgr.get_approval("tx_cleanup_001")
        assert record.status == ApprovalStatus.EXPIRED