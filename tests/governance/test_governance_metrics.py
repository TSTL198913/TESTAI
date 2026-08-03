"""P4 治理指标测试 (规则1: 路由/异步任务须注册 Prometheus 计数器+直方图)。

背景: 审计证实 src/governance/ 零 Prometheus 指标, 治理六步闭环完全不可观测,
直接违反用户规则1。本测试覆盖:
- 正向: GovernanceMetrics 注册计数器+直方图, record_* 正确递增
- 依赖: orchestrator.execute_governance_flow / AutoDecisionEngine.evaluate 实际调用指标
- 边界: 不同 status/decision 标签独立计数, 单例
- 负向: 未注册标签不误计
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _counter_value(counter, **labels):
    """读取带标签计数器当前值 (跨测试可能累积, 调用方用 before/after 增量判断)。"""
    return counter.labels(**labels)._value.get()


class TestGovernanceMetricsRegistration:
    """正向: GovernanceMetrics 必须注册治理闭环所需的计数器与直方图。"""

    def test_governance_metrics_class_exists(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        assert m is not None

    def test_flow_counter_and_histogram_registered(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        # 直接访问属性 (属性不存在时 AttributeError 比 hasattr 更早、更明确失败)
        assert m.flow_counter is not None, "缺少治理流程计数器 flow_counter"
        assert m.flow_duration is not None, "缺少治理流程耗时直方图 flow_duration"
        # 标签必须含 status (FIXED/FAILED/SKIPPED/PENDING_APPROVAL/DIAGNOSED)
        # 行为校验: status 标签可接受, 非法标签应抛错
        m.flow_counter.labels(status="FIXED")  # 不抛错即证明 status 是合法标签
        with pytest.raises(ValueError):
            m.flow_counter.labels(not_a_label="x")

    def test_patch_counter_and_histogram_registered(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        assert m.patch_counter is not None, "缺少补丁计数器 patch_counter"
        assert m.patch_duration is not None, "缺少补丁耗时直方图 patch_duration"
        m.patch_counter.labels(status="success")
        with pytest.raises(ValueError):
            m.patch_counter.labels(not_a_label="x")

    def test_decision_counter_registered(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        assert m.decision_counter is not None, "缺少自动决策计数器 decision_counter"
        m.decision_counter.labels(decision="AUTO_APPROVE")
        with pytest.raises(ValueError):
            m.decision_counter.labels(not_a_label="x")


class TestGovernanceMetricsRecording:
    """正向/边界: record_* 方法必须正确递增, 且不同标签独立计数。"""

    def test_record_flow_increments_counter(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        before = _counter_value(m.flow_counter, status="FIXED")
        m.record_flow("FIXED", 0.5)
        after = _counter_value(m.flow_counter, status="FIXED")
        assert after == before + 1, f"record_flow 未递增: {before} -> {after}"

    def test_record_flow_status_labels_independent(self):
        """边界: 不同 status 标签独立计数, 互不干扰。"""
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        b_fixed = _counter_value(m.flow_counter, status="FIXED")
        b_failed = _counter_value(m.flow_counter, status="FAILED")
        m.record_flow("FIXED", 0.1)
        assert _counter_value(m.flow_counter, status="FIXED") == b_fixed + 1
        assert _counter_value(m.flow_counter, status="FAILED") == b_failed, (
            "FIXED 递增不应影响 FAILED 计数"
        )

    def test_record_patch_increments_counter(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        before = _counter_value(m.patch_counter, status="success")
        m.record_patch("success", 0.2)
        assert _counter_value(m.patch_counter, status="success") == before + 1

    def test_record_decision_increments_counter(self):
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        before = _counter_value(m.decision_counter, decision="AUTO_APPROVE")
        m.record_decision("AUTO_APPROVE")
        assert _counter_value(m.decision_counter, decision="AUTO_APPROVE") == before + 1

    def test_record_flow_observes_duration(self):
        """正向: 耗时直方图必须 observe 时长 (不抛错即视为接入, 直方图无简单值读取)。"""
        from src.governance.metrics import GovernanceMetrics
        m = GovernanceMetrics()
        # 多次 observe 不同时长, 不抛异常即通过
        for d in (0.01, 0.1, 1.0, 10.0):
            m.record_flow("FIXED", d)
            m.record_patch("success", d)


class TestGovernanceMetricsSingleton:
    """边界: GovernanceMetrics 必须是单例 (避免重复注册同名指标触发 ValueError)。"""

    def test_singleton_returns_same_instance(self):
        from src.governance.metrics import GovernanceMetrics
        a = GovernanceMetrics()
        b = GovernanceMetrics()
        assert a is b, "GovernanceMetrics 必须单例, 否则重复注册 prometheus 指标"


class TestOrchestratorFlowMetricIntegration:
    """依赖: orchestrator.execute_governance_flow 必须实际调用 record_flow。"""

    def test_flow_metric_incremented_on_skipped_flow(self):
        """用不可修复诊断触发 SKIPPED 分支 (不写文件), 验证 flow_counter 递增。"""
        from src.governance.orchestrator import GovernanceOrchestrator
        from src.governance.models import DiagnosticContext

        orch = GovernanceOrchestrator()
        # mock agent 返回不可修复诊断 -> 走 SKIPPED 分支, 不触发 apply_patch
        fake_diag = MagicMock(
            is_fixable=False,
            patch_proposal=None,
            confidence_score=0.5,
            reasoning="not fixable",
        )
        orch.agent.analyze_with_context = AsyncMock(return_value=fake_diag)

        before = _counter_value(orch._metrics.flow_counter, status="SKIPPED")
        ctx = DiagnosticContext(
            step_id="metric-test-001",
            component_name="HTTPProcessor",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="ValueError: boom",
        )
        asyncio.run(orch.execute_governance_flow(ctx))
        after = _counter_value(orch._metrics.flow_counter, status="SKIPPED")
        assert after == before + 1, (
            f"execute_governance_flow 未记录流程指标 (SKIPPED): {before} -> {after}"
        )

    def test_flow_metric_incremented_on_failed_agent(self):
        """异常: agent 抛错时流程仍应记录 FAILED 指标, 不得因异常漏记。"""
        from src.governance.orchestrator import GovernanceOrchestrator
        from src.governance.models import DiagnosticContext

        orch = GovernanceOrchestrator()
        orch.agent.analyze_with_context = AsyncMock(side_effect=RuntimeError("agent down"))

        before = _counter_value(orch._metrics.flow_counter, status="FAILED")
        ctx = DiagnosticContext(
            step_id="metric-test-002",
            component_name="HTTPProcessor",
            input_data={},
            actual_output="",
            expected_baseline="",
            exception_trace="TypeError: bad",
        )
        asyncio.run(orch.execute_governance_flow(ctx))
        after = _counter_value(orch._metrics.flow_counter, status="FAILED")
        assert after == before + 1, (
            f"agent 异常时未记录 FAILED 指标: {before} -> {after}"
        )


class TestAutoDecisionMetricIntegration:
    """依赖: AutoDecisionEngine.evaluate 必须实际调用 record_decision。"""

    def test_evaluate_records_decision_metric(self):
        from src.governance.auto_decision_engine import AutoDecisionEngine

        engine = AutoDecisionEngine()
        before = _counter_value(engine._metrics.decision_counter, decision="AUTO_APPROVE")
        engine.evaluate(
            {"confidence": 0.95, "is_fixable": True, "patch_type": "functional"},
            trace_id="metric-eval-001",
        )
        after = _counter_value(engine._metrics.decision_counter, decision="AUTO_APPROVE")
        assert after == before + 1, (
            f"evaluate 未记录决策指标 (AUTO_APPROVE): {before} -> {after}"
        )

    def test_evaluate_records_default_manual_metric(self):
        """边界: 默认 REQUIRE_MANUAL 分支也应记录指标。"""
        from src.governance.auto_decision_engine import AutoDecisionEngine

        engine = AutoDecisionEngine()
        before = _counter_value(engine._metrics.decision_counter, decision="REQUIRE_MANUAL")
        engine.evaluate(
            {"confidence": 0.75, "is_fixable": True, "patch_category": "unknown"},
            trace_id="metric-eval-002",
        )
        after = _counter_value(engine._metrics.decision_counter, decision="REQUIRE_MANUAL")
        assert after == before + 1, (
            f"默认 REQUIRE_MANUAL 分支未记录指标: {before} -> {after}"
        )
