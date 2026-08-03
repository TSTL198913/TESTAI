"""治理历史记录模块。

提供两层历史:
1. 决策级历史 (GovernanceDecision) — AutoDecisionEngine.evaluate 产生的逐条决策,
   供 auto_decision_engine / 审批门查询。内存存储,单例。
2. 运行级历史 (GovernanceRunRecord) — 治理流程 (execute_governance_flow) 每次
   运行的完整状态 (trace_id / component / status / steps),供 orchestrator 记录、
   E2E 测试验证。当 db_path 提供时使用 SQLite 持久化,否则内存存储。

单例模式: GovernanceHistory 在进程内共享。db_path 在首次传入或后续传入时更新,
使测试可以通过 GovernanceHistory(db_path=...) 指定持久化路径,随后 orchestrator
内部 GovernanceHistory() 取到同一实例。
"""
import json
import os
import sqlite3
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


@dataclass
class GovernanceRunRecord:
    """治理流程运行记录 (运行级历史)。"""
    trace_id: str
    component_name: str
    status: str  # STARTED / COMPLETED / FIXED / FAILED / REJECTED / PENDING_APPROVAL / SKIPPED
    start_time: str = ""
    end_time: str = ""
    completed_steps: int = 0
    total_steps: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GovernanceHistory:
    _instance: Optional["GovernanceHistory"] = None
    _lock = threading.RLock()

    # Class-level type annotations for instance attributes.
    # pylint cannot infer attributes set inside __new__, so we declare them
    # here to satisfy E1101 (no-member) across all methods that use them.
    _decisions: List[GovernanceDecision]
    _decisions_lock: threading.RLock
    _runs: List[GovernanceRunRecord]
    _runs_lock: threading.RLock
    _db_path: Optional[str]

    def __new__(cls, db_path: Optional[str] = None, **kwargs) -> "GovernanceHistory":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._decisions = []
                cls._instance._decisions_lock = threading.RLock()
                cls._instance._runs = []
                cls._instance._runs_lock = threading.RLock()
                cls._instance._db_path = None
            # 每次传入 db_path 时更新 (允许测试指定持久化路径)
            if db_path is not None:
                cls._instance._db_path = db_path
                cls._instance._init_db()
            return cls._instance

    # ------------------------------------------------------------------
    # SQLite 持久化 (运行级历史)
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        """初始化 SQLite 表 (若 db_path 已设置)。"""
        if not self._db_path:
            return
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS governance_runs (
                    trace_id       TEXT PRIMARY KEY,
                    component_name TEXT,
                    status         TEXT,
                    start_time     TEXT,
                    end_time       TEXT,
                    completed_steps INTEGER,
                    total_steps    INTEGER,
                    metadata       TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 运行级历史 API
    # ------------------------------------------------------------------
    def record_run(
        self,
        trace_id: str,
        component_name: str = "",
        status: str = "STARTED",
        completed_steps: int = 0,
        total_steps: int = 5,
        end_time: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GovernanceRunRecord:
        """记录或更新一次治理流程运行 (按 trace_id upsert)。

        若 trace_id 已存在则更新状态/步数,否则新建记录。
        start_time 仅在首次创建时设置。
        """
        now = datetime.utcnow().isoformat()
        record = None

        with self._runs_lock:
            # 查找已有记录
            existing = next((r for r in self._runs if r.trace_id == trace_id), None)
            if existing:
                existing.status = status
                existing.component_name = component_name or existing.component_name
                existing.completed_steps = completed_steps or existing.completed_steps
                existing.total_steps = total_steps or existing.total_steps
                if end_time:
                    existing.end_time = end_time
                if metadata:
                    existing.metadata.update(metadata)
                record = existing
            else:
                record = GovernanceRunRecord(
                    trace_id=trace_id,
                    component_name=component_name,
                    status=status,
                    start_time=now,
                    end_time=end_time,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    metadata=metadata or {},
                )
                self._runs.append(record)

        # SQLite 持久化
        if self._db_path:
            self._persist_run(record)
        return record

    _CREATE_RUNS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS governance_runs (
            trace_id       TEXT PRIMARY KEY,
            component_name TEXT,
            status         TEXT,
            start_time     TEXT,
            end_time       TEXT,
            completed_steps INTEGER,
            total_steps    INTEGER,
            metadata       TEXT
        )
    """

    def _persist_run(self, record: GovernanceRunRecord) -> None:
        """将运行记录写入 SQLite (upsert)。

        防御性建表: 即使 db_path 指向的文件被测试清理删除后重建,
        也保证表结构存在,避免 OperationalError 中断治理流程。
        """
        if not self._db_path:
            return
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        try:
            conn.execute(self._CREATE_RUNS_TABLE_SQL)
            conn.execute(
                """
                INSERT OR REPLACE INTO governance_runs
                    (trace_id, component_name, status, start_time,
                     end_time, completed_steps, total_steps, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trace_id,
                    record.component_name,
                    record.status,
                    record.start_time,
                    record.end_time,
                    record.completed_steps,
                    record.total_steps,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_run(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """按 trace_id 获取运行记录 (返回 dict)。"""
        with self._runs_lock:
            for r in self._runs:
                if r.trace_id == trace_id:
                    return r.to_dict()

        # 回退到 SQLite (防御: 表可能尚未创建)
        if self._db_path:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            try:
                conn.execute(self._CREATE_RUNS_TABLE_SQL)
                row = conn.execute(
                    "SELECT trace_id, component_name, status, start_time, "
                    "end_time, completed_steps, total_steps, metadata "
                    "FROM governance_runs WHERE trace_id = ?",
                    (trace_id,),
                ).fetchone()
                if row:
                    return self._row_to_dict(row)
            except sqlite3.OperationalError as e:
                # 表缺失或 DB 不可读 — 降级返回内存结果 (已为 None)
                pass
            finally:
                conn.close()
        return None

    def get_recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的运行记录 (按时间倒序,返回 dict 列表)。"""
        with self._runs_lock:
            runs = sorted(
                self._runs,
                key=lambda r: r.start_time,
                reverse=True,
            )[:limit]
            return [r.to_dict() for r in runs]

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        """SQLite 行转 dict。"""
        try:
            meta = json.loads(row[7]) if row[7] else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        return {
            "trace_id": row[0],
            "component_name": row[1],
            "status": row[2],
            "start_time": row[3],
            "end_time": row[4],
            "completed_steps": row[5],
            "total_steps": row[6],
            "metadata": meta,
        }

    def clear_runs(self) -> None:
        """清空运行级历史 (内存 + SQLite)。"""
        with self._runs_lock:
            self._runs.clear()
        if self._db_path and os.path.exists(self._db_path):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            try:
                conn.execute(self._CREATE_RUNS_TABLE_SQL)
                conn.execute("DELETE FROM governance_runs")
                conn.commit()
            except sqlite3.OperationalError:
                # 表缺失 — 无需清理,直接返回
                pass
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # 决策级历史 API (供 AutoDecisionEngine 使用)
    # ------------------------------------------------------------------
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
        """清空决策级历史 (保持向后兼容)。"""
        with self._decisions_lock:
            self._decisions.clear()

    def count(self) -> int:
        with self._decisions_lock:
            return len(self._decisions)
