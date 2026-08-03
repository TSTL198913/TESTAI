# src/governance/metrics.py
"""治理六步闭环 Prometheus 指标 (用户规则1: 路由/异步任务须注册计数器+直方图)。

审计证实 src/governance/ 此前零 Prometheus 指标, 治理闭环完全不可观测。
本模块注册治理流程/补丁/自动决策三类指标的计数器与耗时直方图, 供
orchestrator / executor / auto_decision_engine 接入。

设计:
- GovernanceMetrics 为单例 (与 APIMetrics 一致), 避免重复注册同名指标触发
  prometheus_client 的 ValueError。
- flow: 治理流程 (execute_governance_flow) 按 status (FIXED/FAILED/SKIPPED/
  PENDING_APPROVAL/DIAGNOSED) 计数 + 耗时。
- patch: 补丁应用 (apply_patch) 按 status (success/failed) 计数 + 耗时。
- decision: 自动决策 (AutoDecisionEngine.evaluate) 按 decision 类型计数。
"""
import threading

from prometheus_client import Counter, Histogram  # pylint: disable=import-error


class GovernanceMetrics:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.flow_counter = Counter(
            "testai_governance_flow_total",
            "治理流程执行总次数 (六步闭环)",
            ["status"],
        )
        self.flow_duration = Histogram(
            "testai_governance_flow_duration_seconds",
            "治理流程耗时 (秒)",
            ["status"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
        )

        self.patch_counter = Counter(
            "testai_governance_patch_total",
            "补丁应用总次数",
            ["status"],
        )
        self.patch_duration = Histogram(
            "testai_governance_patch_duration_seconds",
            "补丁应用耗时 (秒)",
            ["status"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
        )

        self.decision_counter = Counter(
            "testai_governance_decision_total",
            "自动决策次数 (按决策类型)",
            ["decision"],
        )

        self._initialized = True

    def record_flow(self, status: str, duration: float) -> None:
        """记录一次治理流程执行 (按最终 status)。"""
        self.flow_counter.labels(status=status).inc()
        self.flow_duration.labels(status=status).observe(duration)

    def record_patch(self, status: str, duration: float) -> None:
        """记录一次补丁应用 (success/failed)。"""
        self.patch_counter.labels(status=status).inc()
        self.patch_duration.labels(status=status).observe(duration)

    def record_decision(self, decision: str) -> None:
        """记录一次自动决策 (按 decision 类型)。"""
        self.decision_counter.labels(decision=decision).inc()
