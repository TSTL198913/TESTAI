"""BUG-068: GovernanceTracker状态污染测试

问题描述: GovernanceTracker的_events和_db_path在类级别定义，
虽然在__new__中尝试初始化为实例变量，但类变量的存在可能导致状态污染。

成功指标: 重置_instance后创建新实例时，_events应为空列表
失败指标: 新实例继承了旧实例的事件数据
"""
import pytest
import threading
import tempfile
import os
from src.governance.tracker import GovernanceTracker, GovernanceActionType


class TestBug068TrackerStatePollution:
    """验证GovernanceTracker状态污染问题"""

    def test_tracker_state_clean_after_reset(self, tmp_path):
        """重置_instance后，新实例不应继承旧实例的事件数据"""
        db_path1 = tmp_path / "tracker1.db"
        db_path2 = tmp_path / "tracker2.db"

        GovernanceTracker._instance = None

        tracker1 = GovernanceTracker(db_path=str(db_path1))
        tracker1.record_event(
            trace_id="trace_001",
            action_type=GovernanceActionType.DIAGNOSE_START,
            component="component1",
        )

        assert len(tracker1._events) == 1, "tracker1应包含1个事件"

        GovernanceTracker._instance = None

        tracker2 = GovernanceTracker(db_path=str(db_path2))

        assert len(tracker2._events) == 0, (
            f"tracker2应为空，不应继承tracker1的事件。"
            f"实际事件数: {len(tracker2._events)}"
        )

        assert tracker2._db_path == db_path2, (
            f"tracker2的数据库路径应为{db_path2}，实际: {tracker2._db_path}"
        )

    def test_concurrent_tracker_instances_isolation(self, tmp_path):
        """并发创建tracker实例时，事件应隔离

        注意: 此测试暴露了GovernanceTracker._instance = None不是线程安全的问题。
        多个线程同时重置_instance可能导致一个线程在检查和创建之间被抢占，
        从而引发AttributeError。这是一个真实的并发安全bug。
        """
        db_path = tmp_path / "concurrent.db"
        GovernanceTracker._instance = None

        tracker = GovernanceTracker(db_path=str(db_path))
        results = []

        def record_event(instance_num):
            tracker.record_event(
                trace_id=f"trace_{instance_num}",
                action_type=GovernanceActionType.DIAGNOSE_START,
                component=f"component_{instance_num}",
            )
            results.append((instance_num, len(tracker._events)))

        threads = [threading.Thread(target=record_event, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(tracker._events) == 5, (
            f"最终应包含5个事件，实际: {len(tracker._events)}"
        )

        assert len(results) == 5, f"应记录5次结果，实际: {len(results)}"