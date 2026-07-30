"""tests/exposed_bugs/ 共享 fixture。

关键设计:每个测试获得独立的 ApprovalManager / GovernanceTracker 实例,
通过重置单例 + 类变量实现真正隔离,避免现有测试的"类变量污染"反模式。
"""
import os
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def isolated_approval_manager(tmp_path):
    """每个测试独立的 ApprovalManager,完全隔离。

    通过重置单例 + 使用独立 db_path 实现真正隔离。
    _approvals 是实例变量,由 __new__ 在创建实例时初始化。
    """
    from src.governance.approval import ApprovalManager

    ApprovalManager._instance = None

    db_path = tmp_path / "test_approval.db"
    mgr = ApprovalManager(db_path=str(db_path))
    yield mgr

    ApprovalManager._instance = None


@pytest.fixture
def isolated_tracker(tmp_path):
    """每个测试独立的 GovernanceTracker,完全隔离。"""
    from src.governance.tracker import GovernanceTracker

    GovernanceTracker._instance = None
    GovernanceTracker._events = []

    db_path = tmp_path / "test_tracker.db"
    tracker = GovernanceTracker(db_path=str(db_path))
    yield tracker

    GovernanceTracker._instance = None
    GovernanceTracker._events = []


@pytest.fixture
def isolated_alert_manager():
    """每个测试独立的 AlertManager,清空 _alerts 列表。"""
    from src.governance.monitoring import AlertManager

    mgr = AlertManager()
    # 保存原始 alerts
    original_alerts = mgr._alerts.copy()
    mgr._alerts.clear()
    yield mgr
    # 恢复
    mgr._alerts.clear()
    mgr._alerts.extend(original_alerts)


@pytest.fixture
def make_proposal():
    """工厂 fixture:生成 PatchProposal。"""
    from src.governance.models import PatchProposal, PatchType

    def _make(patch_type=PatchType.FUNCTIONAL, target_function="test_func",
              suggested_code="pass"):
        return PatchProposal(
            target_function=target_function,
            suggested_code=suggested_code,
            patch_type=patch_type,
        )
    return _make


@pytest.fixture
def make_context():
    """工厂 fixture:生成 DiagnosticContext。"""
    from src.governance.models import DiagnosticContext

    def _make(step_id="test_step", component_name="test_component",
              input_data=None, actual_output="", expected_baseline="",
              exception_trace=None):
        return DiagnosticContext(
            step_id=step_id,
            component_name=component_name,
            input_data=input_data or {},
            actual_output=actual_output,
            expected_baseline=expected_baseline,
            exception_trace=exception_trace,
        )
    return _make
