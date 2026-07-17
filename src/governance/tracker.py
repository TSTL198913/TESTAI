import logging
import threading
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path

from src.governance.models import DiagnosticContext, PatchProposal, PatchType


class GovernanceActionType(Enum):
    DIAGNOSE_START = "diagnose_start"
    DIAGNOSE_COMPLETE = "diagnose_complete"
    PATCH_CREATE = "patch_create"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    PATCH_APPLIED = "patch_applied"
    PATCH_FAILED = "patch_failed"
    RETRY = "retry"
    ROLLBACK = "rollback"
    CONVERGED = "converged"
    DIVERGED = "diverged"


@dataclass
class TrackingEvent:
    trace_id: str
    action_type: GovernanceActionType
    timestamp: datetime = field(default_factory=datetime.now)
    component: Optional[str] = None
    step_id: Optional[str] = None
    tx_id: Optional[str] = None
    patch_type: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class GovernanceTracker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "data/governance.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._events = []
                    cls._instance._db_path = Path(db_path)
                    cls._instance._db_lock = threading.Lock()
                    cls._instance._init_db()
                    cls._instance._load_from_db()
        return cls._instance

    def _init_db(self):
        with self._db_lock:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tracking_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    component TEXT,
                    step_id TEXT,
                    tx_id TEXT,
                    patch_type TEXT,
                    status TEXT,
                    message TEXT,
                    metadata_json TEXT
                )
            ''')

            conn.commit()
            conn.close()

    def _load_from_db(self):
        with self._db_lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tracking_events ORDER BY id')

            for row in cursor.fetchall():
                _, trace_id, action_type, timestamp, component, \
                step_id, tx_id, patch_type, status, message, metadata_json = row

                event = TrackingEvent(
                    trace_id=trace_id,
                    action_type=GovernanceActionType(action_type),
                    timestamp=datetime.fromisoformat(timestamp),
                    component=component,
                    step_id=step_id,
                    tx_id=tx_id,
                    patch_type=patch_type,
                    status=status,
                    message=message,
                    metadata=json.loads(metadata_json) if metadata_json else {}
                )

                self._events.append(event)

            conn.close()

    def _save_to_db(self, event: TrackingEvent):
        with self._db_lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO tracking_events
                (trace_id, action_type, timestamp, component, step_id,
                 tx_id, patch_type, status, message, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.trace_id,
                event.action_type.value,
                event.timestamp.isoformat(),
                event.component,
                event.step_id,
                event.tx_id,
                event.patch_type,
                event.status,
                event.message,
                json.dumps(event.metadata)
            ))

            conn.commit()
            conn.close()

    def record_event(
        self,
        trace_id: str,
        action_type: GovernanceActionType,
        component: Optional[str] = None,
        step_id: Optional[str] = None,
        tx_id: Optional[str] = None,
        patch_type: Optional[PatchType] = None,
        status: Optional[str] = None,
        message: Optional[str] = None,
        **metadata
    ):
        event = TrackingEvent(
            trace_id=trace_id,
            action_type=action_type,
            component=component,
            step_id=step_id,
            tx_id=tx_id,
            patch_type=patch_type.value if patch_type else None,
            status=status,
            message=message,
            metadata=metadata
        )

        with self._lock:
            self._events.append(event)

        self._save_to_db(event)
        logging.info(f"[TRACKER] {action_type.value} | trace={trace_id} | component={component} | status={status}")

    def get_events_by_trace(self, trace_id: str) -> List[TrackingEvent]:
        with self._lock:
            return [e for e in self._events if e.trace_id == trace_id]

    def get_events_by_component(self, component: str) -> List[TrackingEvent]:
        with self._lock:
            return [e for e in self._events if e.component == component]

    def get_events_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[TrackingEvent]:
        with self._lock:
            return [
                e for e in self._events
                if start_time <= e.timestamp <= end_time
            ]

    def get_events_by_action(self, action_type: GovernanceActionType) -> List[TrackingEvent]:
        with self._lock:
            return [e for e in self._events if e.action_type == action_type]

    def get_recent_events(self, limit: int = 50) -> List[TrackingEvent]:
        with self._lock:
            return self._events[-limit:]

    def get_summary(self, trace_id: str = None) -> Dict:
        with self._lock:
            events = self._events if trace_id is None else self.get_events_by_trace(trace_id)

        stats = {
            "total_events": len(events),
            "by_action": {},
            "by_component": {},
            "by_status": {},
            "converged_count": 0,
            "diverged_count": 0,
            "failed_count": 0
        }

        for action in GovernanceActionType:
            stats["by_action"][action.value] = 0

        for event in events:
            stats["by_action"][event.action_type.value] += 1

            if event.component:
                stats["by_component"][event.component] = stats["by_component"].get(event.component, 0) + 1

            if event.status:
                stats["by_status"][event.status] = stats["by_status"].get(event.status, 0) + 1

            if event.action_type == GovernanceActionType.CONVERGED:
                stats["converged_count"] += 1
            elif event.action_type == GovernanceActionType.DIVERGED:
                stats["diverged_count"] += 1
            elif event.action_type == GovernanceActionType.PATCH_FAILED:
                stats["failed_count"] += 1

        return stats

    def clear(self):
        with self._lock:
            self._events.clear()

        with self._db_lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tracking_events')
            conn.commit()
            conn.close()

    def export_events(self, trace_id: str = None) -> List[Dict]:
        with self._lock:
            events = self._events if trace_id is None else self.get_events_by_trace(trace_id)

        return [
            {
                "trace_id": e.trace_id,
                "action_type": e.action_type.value,
                "timestamp": e.timestamp.isoformat(),
                "component": e.component,
                "step_id": e.step_id,
                "tx_id": e.tx_id,
                "patch_type": e.patch_type,
                "status": e.status,
                "message": e.message,
                "metadata": e.metadata
            }
            for e in events
        ]