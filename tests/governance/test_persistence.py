import os
from pathlib import Path

import pytest

from src.governance.models import DiagnosticContext, PatchProposal, PatchType
from src.governance.tracker import GovernanceActionType
from tests.governance.persistence import (
    PersistentApprovalManager,
    PersistentGovernanceTracker,
)


@pytest.fixture
def temp_db():
    db_path = "tests/data/test_governance.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


class TestPersistentApprovalManager:
    def test_create_approval_persists(self, temp_db):
        mgr = PersistentApprovalManager(db_path=temp_db)

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step_001",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        mgr.create_approval("tx_persist_001", proposal, context)

        records = mgr.get_all_records()
        assert len(records) == 1
        assert records[0][0] == "tx_persist_001"
        assert records[0][1] == "pending"

    def test_approval_survives_reinstantiation(self, temp_db):
        mgr1 = PersistentApprovalManager(db_path=temp_db)

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step_002",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        mgr1.create_approval("tx_reinstantiate_001", proposal, context)
        mgr1.approve("tx_reinstantiate_001", "tech_committee", "Approved")

        mgr2 = PersistentApprovalManager(db_path=temp_db)

        record = mgr2.get_approval("tx_reinstantiate_001")
        assert record is not None
        assert record.status.value == "approved"
        assert record.approved_by == "tech_committee"

    def test_reject_persists(self, temp_db):
        mgr = PersistentApprovalManager(db_path=temp_db)

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step_003",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        mgr.create_approval("tx_reject_001", proposal, context)
        mgr.reject("tx_reject_001", "tech_committee", "Risky")

        records = mgr.get_all_records()
        assert len(records) == 1
        assert records[0][1] == "rejected"

    def test_multiple_approvals(self, temp_db):
        mgr = PersistentApprovalManager(db_path=temp_db)

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step_004",
            component_name="TestComponent",
            input_data={},
            actual_output="",
            expected_baseline="",
        )

        for i in range(5):
            mgr.create_approval(f"tx_multi_{i}", proposal, context)

        records = mgr.get_all_records()
        assert len(records) == 5


class TestPersistentGovernanceTracker:
    def test_record_event_persists(self, temp_db):
        tracker = PersistentGovernanceTracker(db_path=temp_db)

        tracker.record_event(
            trace_id="trace_persist_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="TestComponent",
            status="STARTED",
        )

        count = tracker.get_event_count()
        assert count == 1

    def test_event_survives_reinstantiation(self, temp_db):
        tracker1 = PersistentGovernanceTracker(db_path=temp_db)

        tracker1.record_event(
            trace_id="trace_reinstantiate_001",
            action_type=GovernanceActionType.PATCH_APPLIED,
            component="TestComponent",
            status="FIXED",
        )

        tracker2 = PersistentGovernanceTracker(db_path=temp_db)

        events = tracker2.get_events_by_trace("trace_reinstantiate_001")
        assert len(events) == 1
        assert events[0].action_type == GovernanceActionType.PATCH_APPLIED
        assert events[0].status == "FIXED"

    def test_multiple_events(self, temp_db):
        tracker = PersistentGovernanceTracker(db_path=temp_db)

        for i in range(10):
            tracker.record_event(
                trace_id=f"trace_multi_{i}",
                action_type=GovernanceActionType.DIAGNOSE_START,
                component="TestComponent",
            )

        count = tracker.get_event_count()
        assert count == 10

    def test_clear_removes_events(self, temp_db):
        tracker = PersistentGovernanceTracker(db_path=temp_db)

        tracker.record_event(
            trace_id="trace_clear_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="TestComponent",
        )

        assert tracker.get_event_count() == 1

        tracker.clear()

        assert tracker.get_event_count() == 0

    def test_summary_persists(self, temp_db):
        tracker1 = PersistentGovernanceTracker(db_path=temp_db)

        tracker1.record_event(
            trace_id="trace_summary_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
        )
        tracker1.record_event(
            trace_id="trace_summary_001", action_type=GovernanceActionType.PATCH_APPLIED
        )

        tracker2 = PersistentGovernanceTracker(db_path=temp_db)
        summary = tracker2.get_summary()

        assert summary["total_events"] == 2
        assert summary["by_action"]["diagnose_start"] == 1
        assert summary["by_action"]["patch_applied"] == 1
