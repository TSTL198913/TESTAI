import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from src.governance.approval import (ApprovalManager, ApprovalRecord,
                                     ApprovalStatus)
from src.governance.tracker import (GovernanceActionType, GovernanceTracker,
                                    TrackingEvent)


class PersistentApprovalManager:
    def __init__(self, db_path: str = "tests/data/governance.db"):
        self._lock = threading.Lock()
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._inner = ApprovalManager()
        self._load_from_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS approval_records (
                    tx_id TEXT PRIMARY KEY,
                    proposal_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    reason TEXT,
                    expires_at TEXT NOT NULL
                )
            ''')

            conn.commit()
            conn.close()

    def _load_from_db(self):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM approval_records')

            for row in cursor.fetchall():
                tx_id, proposal_json, context_json, status, created_at, \
                approved_by, approved_at, reason, expires_at = row

                from src.governance.models import (DiagnosticContext,
                                                   PatchProposal)
                proposal = PatchProposal.model_validate_json(proposal_json)
                context = DiagnosticContext.model_validate_json(context_json)

                record = ApprovalRecord(tx_id, proposal, context)
                record.status = ApprovalStatus(status)
                record.created_at = datetime.fromisoformat(created_at)
                record.approved_by = approved_by
                record.approved_at = datetime.fromisoformat(approved_at) if approved_at else None
                record.reason = reason
                record.expires_at = datetime.fromisoformat(expires_at)

                with self._inner._lock:
                    self._inner._approvals[tx_id] = record

            conn.close()

    def _save_to_db(self, record: ApprovalRecord):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO approval_records
                (tx_id, proposal_json, context_json, status, created_at,
                 approved_by, approved_at, reason, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.tx_id,
                record.proposal.model_dump_json(),
                record.context.model_dump_json(),
                record.status.value,
                record.created_at.isoformat(),
                record.approved_by,
                record.approved_at.isoformat() if record.approved_at else None,
                record.reason,
                record.expires_at.isoformat()
            ))

            conn.commit()
            conn.close()

    def create_approval(self, tx_id, proposal, context):
        record = self._inner.create_approval(tx_id, proposal, context)
        self._save_to_db(record)
        return record

    def get_approval(self, tx_id):
        record = self._inner.get_approval(tx_id)
        if record:
            self._save_to_db(record)
        return record

    def approve(self, tx_id, approver, reason=None):
        result = self._inner.approve(tx_id, approver, reason)
        if result:
            record = self._inner.get_approval(tx_id)
            self._save_to_db(record)
        return result

    def reject(self, tx_id, approver, reason):
        result = self._inner.reject(tx_id, approver, reason)
        if result:
            record = self._inner.get_approval(tx_id)
            self._save_to_db(record)
        return result

    def requires_approval(self, tx_id):
        return self._inner.requires_approval(tx_id)

    def is_approved(self, tx_id):
        return self._inner.is_approved(tx_id)

    def list_pending(self):
        return self._inner.list_pending()

    def cleanup_expired(self):
        result = self._inner.cleanup_expired()
        for tx_id, record in list(self._inner._approvals.items()):
            self._save_to_db(record)
        return result

    def get_all_records(self):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('SELECT tx_id, status, created_at FROM approval_records')
            results = cursor.fetchall()
            conn.close()
            return results


class PersistentGovernanceTracker:
    def __init__(self, db_path: str = "tests/data/governance.db"):
        self._lock = threading.Lock()
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._inner = GovernanceTracker()
        self._load_from_db()

    def _init_db(self):
        with self._lock:
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
        with self._lock:
            with self._inner._lock:
                self._inner._events.clear()

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

                with self._inner._lock:
                    self._inner._events.append(event)

            conn.close()

    def _save_to_db(self, event: TrackingEvent):
        with self._lock:
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

    def record_event(self, trace_id, action_type, component=None, step_id=None,
                     tx_id=None, patch_type=None, status=None, message=None, **metadata):
        self._inner.record_event(
            trace_id, action_type, component, step_id, tx_id,
            patch_type, status, message, **metadata
        )
        events = self._inner.get_events_by_trace(trace_id)
        if events:
            self._save_to_db(events[-1])

    def get_events_by_trace(self, trace_id):
        return self._inner.get_events_by_trace(trace_id)

    def get_events_by_component(self, component):
        return self._inner.get_events_by_component(component)

    def get_events_by_time_range(self, start_time, end_time):
        return self._inner.get_events_by_time_range(start_time, end_time)

    def get_events_by_action(self, action_type):
        return self._inner.get_events_by_action(action_type)

    def get_recent_events(self, limit=50):
        return self._inner.get_recent_events(limit)

    def get_summary(self, trace_id=None):
        return self._inner.get_summary(trace_id)

    def clear(self):
        self._inner.clear()
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tracking_events')
            conn.commit()
            conn.close()

    def export_events(self, trace_id=None):
        return self._inner.export_events(trace_id)

    def get_event_count(self):
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM tracking_events')
            count = cursor.fetchone()[0]
            conn.close()
            return count