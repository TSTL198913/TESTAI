import pytest
import threading
import tempfile
import os
from src.governance.tracker import GovernanceTracker, GovernanceActionType


class TestGovernanceTrackerClassVar:
    def test_events_is_not_class_variable(self, tmp_path):
        db_path1 = tmp_path / "test_tracker1.db"
        db_path2 = tmp_path / "test_tracker2.db"

        GovernanceTracker._instance = None

        tracker1 = GovernanceTracker(db_path=str(db_path1))
        tracker1.record_event(
            trace_id="test_trace",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="test_component",
        )

        assert len(tracker1._events) == 1

        GovernanceTracker._instance = None

        tracker2 = GovernanceTracker(db_path=str(db_path2))
        assert len(tracker2._events) == 0, "Events should be instance variable, not class variable"

    def test_db_lock_not_recreated_in_new(self, tmp_path):
        db_path1 = tmp_path / "test_tracker3.db"
        db_path2 = tmp_path / "test_tracker4.db"

        GovernanceTracker._instance = None
        tracker1 = GovernanceTracker(db_path=str(db_path1))
        lock_id_1 = id(tracker1._db_lock)

        GovernanceTracker._instance = None
        tracker2 = GovernanceTracker(db_path=str(db_path2))
        lock_id_2 = id(tracker2._db_lock)

        assert lock_id_1 != lock_id_2, "Each instance should have its own db_lock"