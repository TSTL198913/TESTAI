import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from src.governance.models import DiagnosticContext, PatchProposal


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRecord:
    def __init__(self, tx_id: str, proposal: PatchProposal, context: DiagnosticContext):
        self.tx_id = tx_id
        self.proposal = proposal
        self.context = context
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now()
        self.approved_by: Optional[str] = None
        self.approved_at: Optional[datetime] = None
        self.reason: Optional[str] = None
        self.expires_at = self.created_at + timedelta(minutes=30)

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    @property
    def requires_approval(self) -> bool:
        from src.governance.models import PatchType
        return self.proposal.patch_type in [PatchType.SECURITY, PatchType.REFACTORING]
    
    def _is_large_change(self) -> bool:
        code = self.proposal.suggested_code or ""
        return len(code.splitlines()) > 20


class ApprovalManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, db_path: str = "data/governance.db"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._approvals: Dict[str, ApprovalRecord] = {}
                cls._instance._db_path = Path(db_path)
                cls._instance._db_lock = threading.Lock()
                cls._instance._init_db()
                cls._instance._load_from_db()
        return cls._instance

    def __init__(self, db_path: str = "data/governance.db"):
        if hasattr(self, '_initialized'):
            return
        self._logger = logging.getLogger("ApprovalManager")
        self._initialized = True

    def _init_db(self):
        with self._db_lock:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
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
            with self._db_lock:
                conn = sqlite3.connect(str(self._db_path))
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM approval_records')

                for row in cursor.fetchall():
                    tx_id, proposal_json, context_json, status, created_at, \
                    approved_by, approved_at, reason, expires_at = row

                    proposal = PatchProposal.model_validate_json(proposal_json)
                    context = DiagnosticContext.model_validate_json(context_json)

                    record = ApprovalRecord(tx_id, proposal, context)
                    record.status = ApprovalStatus(status)
                    record.created_at = datetime.fromisoformat(created_at)
                    record.approved_by = approved_by
                    record.approved_at = datetime.fromisoformat(approved_at) if approved_at else None
                    record.reason = reason
                    record.expires_at = datetime.fromisoformat(expires_at)

                    self._approvals[tx_id] = record

                conn.close()

    def _save_to_db(self, record: ApprovalRecord):
        with self._lock:
            with self._db_lock:
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

    def create_approval(self, tx_id: str, proposal: PatchProposal, context: DiagnosticContext) -> ApprovalRecord:
        record = ApprovalRecord(tx_id, proposal, context)
        with self._lock:
            self._approvals[tx_id] = record
        self._save_to_db(record)
        self._logger.info(f"[APPROVAL] Created approval record: {tx_id} ({proposal.patch_type.value})")
        return record

    def get_approval(self, tx_id: str) -> Optional[ApprovalRecord]:
        with self._lock:
            record = self._approvals.get(tx_id)
            if record and record.is_expired:
                record.status = ApprovalStatus.EXPIRED
                self._save_to_db(record)
                self._logger.warning(f"[APPROVAL] Approval expired: {tx_id}")
            return record

    def approve(self, tx_id: str, approver: str, reason: Optional[str] = None) -> bool:
        with self._lock:
            record = self._approvals.get(tx_id)
            if not record:
                return False
            if record.status != ApprovalStatus.PENDING:
                return False
            if record.is_expired:
                record.status = ApprovalStatus.EXPIRED
                self._save_to_db(record)
                return False

            record.status = ApprovalStatus.APPROVED
            record.approved_by = approver
            record.approved_at = datetime.now()
            record.reason = reason

            self._save_to_db(record)

        self._logger.info(f"[APPROVAL] Approved by {approver}: {tx_id}")
        return True

    def reject(self, tx_id: str, approver: str, reason: str) -> bool:
        with self._lock:
            record = self._approvals.get(tx_id)
            if not record:
                return False
            if record.status != ApprovalStatus.PENDING:
                return False

            record.status = ApprovalStatus.REJECTED
            record.approved_by = approver
            record.approved_at = datetime.now()
            record.reason = reason

            self._save_to_db(record)

        self._logger.info(f"[APPROVAL] Rejected by {approver}: {tx_id} - {reason}")
        return True

    def requires_approval(self, tx_id: str) -> bool:
        record = self.get_approval(tx_id)
        if not record:
            return False
        if record.is_expired:
            return False
        return record.requires_approval

    def is_approved(self, tx_id: str) -> bool:
        record = self.get_approval(tx_id)
        return record is not None and record.status == ApprovalStatus.APPROVED

    def list_pending(self) -> list[ApprovalRecord]:
        with self._lock:
            return [r for r in self._approvals.values() if r.status == ApprovalStatus.PENDING and not r.is_expired]

    def cleanup_expired(self):
        with self._lock:
            expired_ids = [tx_id for tx_id, record in self._approvals.items() if record.is_expired]
            for tx_id in expired_ids:
                self._approvals[tx_id].status = ApprovalStatus.EXPIRED
                self._save_to_db(self._approvals[tx_id])
                self._logger.info(f"[APPROVAL] Cleaned up expired: {tx_id}")