import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class GovernanceDecision:
    decision_id: str
    trace_id: str
    decision_type: str
    decision: str
    reason: str
    confidence: float
    auto_approved: bool
    rule_triggered: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GovernanceHistory:
    _instance: Optional["GovernanceHistory"] = None
    _lock = threading.RLock()

    def __new__(cls) -> "GovernanceHistory":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._decisions: List[GovernanceDecision] = []
                cls._instance._decisions_lock = threading.RLock()
            return cls._instance

    def record_decision(self, decision: GovernanceDecision) -> None:
        with self._decisions_lock:
            self._decisions.append(decision)

    def get_decision(self, decision_id: str) -> Optional[GovernanceDecision]:
        with self._decisions_lock:
            for d in self._decisions:
                if d.decision_id == decision_id:
                    return d
        return None

    def get_decisions_by_trace(self, trace_id: str) -> List[GovernanceDecision]:
        with self._decisions_lock:
            return [d for d in self._decisions if d.trace_id == trace_id]

    def get_decision_by_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._decisions_lock:
            return [d.to_dict() for d in self._decisions if d.trace_id == trace_id]

    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._decisions_lock:
            recent = self._decisions[-limit:]
            return [d.to_dict() for d in recent]

    def get_all_decisions(self) -> List[GovernanceDecision]:
        with self._decisions_lock:
            return list(self._decisions)

    def get_summary(self) -> Dict[str, Any]:
        with self._decisions_lock:
            total = len(self._decisions)
            auto_approved = sum(1 for d in self._decisions if d.auto_approved)
            decision_counts: Dict[str, int] = {}
            for d in self._decisions:
                decision_counts[d.decision] = decision_counts.get(d.decision, 0) + 1
            return {
                "total_decisions": total,
                "auto_approved_rate": auto_approved / total if total > 0 else 0.0,
                "decision_counts": decision_counts,
            }

    def clear(self) -> None:
        with self._decisions_lock:
            self._decisions.clear()

    def count(self) -> int:
        with self._decisions_lock:
            return len(self._decisions)
