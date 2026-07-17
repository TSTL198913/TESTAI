import pytest
from datetime import datetime, timedelta
from src.governance.tracker import GovernanceTracker, GovernanceActionType, TrackingEvent
from src.governance.models import PatchType


class TestGovernanceActionType:
    def test_action_types(self):
        assert GovernanceActionType.DIAGNOSE_START.value == "diagnose_start"
        assert GovernanceActionType.DIAGNOSE_COMPLETE.value == "diagnose_complete"
        assert GovernanceActionType.PATCH_CREATE.value == "patch_create"
        assert GovernanceActionType.APPROVAL_REQUIRED.value == "approval_required"
        assert GovernanceActionType.APPROVAL_GRANTED.value == "approval_granted"
        assert GovernanceActionType.APPROVAL_REJECTED.value == "approval_rejected"
        assert GovernanceActionType.PATCH_APPLIED.value == "patch_applied"
        assert GovernanceActionType.PATCH_FAILED.value == "patch_failed"


class TestTrackingEvent:
    def test_event_creation(self):
        event = TrackingEvent(
            trace_id="trace_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="TestComponent",
            step_id="step_001",
            tx_id="tx_001",
            patch_type="functional",
            status="STARTED",
            message="Starting diagnosis"
        )

        assert event.trace_id == "trace_001"
        assert event.action_type == GovernanceActionType.DIAGNOSE_START
        assert event.component == "TestComponent"
        assert event.step_id == "step_001"
        assert event.tx_id == "tx_001"
        assert event.patch_type == "functional"
        assert event.status == "STARTED"
        assert event.message == "Starting diagnosis"


class TestGovernanceTracker:
    def setup_method(self):
        tracker = GovernanceTracker()
        tracker.clear()

    def test_tracker_singleton(self):
        t1 = GovernanceTracker()
        t2 = GovernanceTracker()
        assert t1 is t2

    def test_record_event(self):
        tracker = GovernanceTracker()
        tracker.record_event(
            trace_id="trace_record_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="TestComponent",
            step_id="step_001",
            status="STARTED"
        )

        events = tracker.get_events_by_trace("trace_record_001")
        assert len(events) == 1
        assert events[0].action_type == GovernanceActionType.DIAGNOSE_START
        assert events[0].component == "TestComponent"

    def test_record_event_with_patch_type(self):
        tracker = GovernanceTracker()
        tracker.record_event(
            trace_id="trace_patch_001",
            action_type=GovernanceActionType.PATCH_CREATE,
            component="TestComponent",
            tx_id="tx_001",
            patch_type=PatchType.SECURITY
        )

        events = tracker.get_events_by_trace("trace_patch_001")
        assert len(events) == 1
        assert events[0].patch_type == "security"

    def test_get_events_by_trace(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_filter_001",
            action_type=GovernanceActionType.DIAGNOSE_START
        )
        tracker.record_event(
            trace_id="trace_filter_001",
            action_type=GovernanceActionType.DIAGNOSE_COMPLETE
        )
        tracker.record_event(
            trace_id="trace_filter_002",
            action_type=GovernanceActionType.DIAGNOSE_START
        )

        events = tracker.get_events_by_trace("trace_filter_001")
        assert len(events) == 2

    def test_get_events_by_component(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="ComponentA"
        )
        tracker.record_event(
            trace_id="trace_002",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="ComponentB"
        )
        tracker.record_event(
            trace_id="trace_003",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="ComponentA"
        )

        events = tracker.get_events_by_component("ComponentA")
        assert len(events) == 2

    def test_get_event_by_action(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.DIAGNOSE_START
        )
        tracker.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.PATCH_APPLIED
        )
        tracker.record_event(
            trace_id="trace_002",
            action_type=GovernanceActionType.PATCH_FAILED
        )

        applied_events = tracker.get_events_by_action(GovernanceActionType.PATCH_APPLIED)
        assert len(applied_events) == 1

    def test_get_recent_events(self):
        tracker = GovernanceTracker()

        for i in range(60):
            tracker.record_event(
                trace_id=f"trace_{i}",
                action_type=GovernanceActionType.DIAGNOSE_START
            )

        recent = tracker.get_recent_events(limit=50)
        assert len(recent) == 50

    def test_get_summary(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="CompA",
            status="STARTED"
        )
        tracker.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.PATCH_APPLIED,
            component="CompA",
            status="FIXED"
        )
        tracker.record_event(
            trace_id="trace_002",
            action_type=GovernanceActionType.PATCH_FAILED,
            component="CompB",
            status="FAILED"
        )
        tracker.record_event(
            trace_id="trace_003",
            action_type=GovernanceActionType.CONVERGED,
            component="CompA",
            status="CONVERGED"
        )

        summary = tracker.get_summary()

        assert summary["total_events"] == 4
        assert summary["by_action"]["diagnose_start"] == 1
        assert summary["by_action"]["patch_applied"] == 1
        assert summary["by_action"]["patch_failed"] == 1
        assert summary["by_action"]["converged"] == 1
        assert summary["by_component"]["CompA"] == 3
        assert summary["by_component"]["CompB"] == 1
        assert summary["by_status"]["STARTED"] == 1
        assert summary["by_status"]["FIXED"] == 1
        assert summary["converged_count"] == 1
        assert summary["failed_count"] == 1

    def test_get_summary_by_trace(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_summary_001",
            action_type=GovernanceActionType.DIAGNOSE_START
        )
        tracker.record_event(
            trace_id="trace_summary_001",
            action_type=GovernanceActionType.PATCH_APPLIED
        )
        tracker.record_event(
            trace_id="trace_summary_002",
            action_type=GovernanceActionType.DIAGNOSE_START
        )

        summary = tracker.get_summary(trace_id="trace_summary_001")
        assert summary["total_events"] == 2

    def test_export_events(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_export_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="TestComponent",
            step_id="step_001"
        )

        exported = tracker.export_events()
        assert len(exported) == 1
        assert exported[0]["trace_id"] == "trace_export_001"
        assert exported[0]["action_type"] == "diagnose_start"
        assert exported[0]["component"] == "TestComponent"

    def test_export_events_by_trace(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_export_filter_001",
            action_type=GovernanceActionType.DIAGNOSE_START
        )
        tracker.record_event(
            trace_id="trace_export_filter_002",
            action_type=GovernanceActionType.DIAGNOSE_START
        )

        exported = tracker.export_events(trace_id="trace_export_filter_001")
        assert len(exported) == 1

    def test_clear(self):
        tracker = GovernanceTracker()

        tracker.record_event(
            trace_id="trace_clear_001",
            action_type=GovernanceActionType.DIAGNOSE_START
        )
        assert len(tracker.get_recent_events()) == 1

        tracker.clear()
        assert len(tracker.get_recent_events()) == 0