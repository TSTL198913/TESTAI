"""BUG-062: GoldenBaselineManager 线程安全缺失 - 部分方法无锁保护。

源码位置: src/governance/baseline.py:33-177 GoldenBaselineManager

根因:
1. get_baseline、get_baselines_by_type、get_all_baseline_ids、get_all_baselines 无锁保护
2. add_baseline 有锁但其他读取方法无锁，存在读写竞态条件
3. validate_against_baseline 和 calculate_convergence_score 在调用 get_baseline 时无锁

正确行为:
- 所有对 self._baselines 的读写操作必须用锁保护
- add_baseline 和读取方法应使用相同的锁
"""
import pytest
import threading
import time

from src.governance.baseline import GoldenBaselineManager, BaselineRecord


class TestGoldenBaselineThreadSafety:
    """GoldenBaselineManager线程安全测试"""

    def setup_method(self):
        GoldenBaselineManager._instance = None

    def teardown_method(self):
        GoldenBaselineManager._instance = None

    def test_add_baseline_concurrent_thread_safe(self):
        """并发添加基线记录时，所有记录应正确存储"""
        baseline_manager = GoldenBaselineManager()
        
        errors = []
        added_count = [0]
        
        def add_baseline_thread(thread_id):
            try:
                for i in range(10):
                    record = BaselineRecord(
                        record_id=f"thread_{thread_id}_baseline_{i}",
                        baseline_type="test",
                        data={"key": f"value_{thread_id}_{i}"},
                    )
                    baseline_manager.add_baseline(record)
                    time.sleep(0.001)
                with threading.Lock():
                    added_count[0] += 10
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=add_baseline_thread, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors occurred: {errors}"
        baseline_count = len(baseline_manager._baselines)
        
        expected_count = added_count[0] + len(baseline_manager.get_all_baseline_ids()) - added_count[0]
        assert baseline_count == added_count[0] + len([b for b in baseline_manager._baselines.values() if not b.record_id.startswith("thread_")]), (
            f"Expected {added_count[0]} additional baselines, got {baseline_count - len([b for b in baseline_manager._baselines.values() if not b.record_id.startswith('thread_')])}"
        )

    def test_get_baseline_during_concurrent_add(self):
        """在并发添加期间查询基线应不崩溃"""
        baseline_manager = GoldenBaselineManager()
        
        errors = []
        
        def write_thread():
            try:
                for i in range(30):
                    record = BaselineRecord(
                        record_id=f"concurrent_baseline_{i}",
                        baseline_type="test",
                        data={"key": f"value_{i}"},
                    )
                    baseline_manager.add_baseline(record)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"Write thread error: {e}")
        
        def read_thread():
            try:
                for _ in range(30):
                    record_ids = baseline_manager.get_all_baseline_ids()
                    assert isinstance(record_ids, list)
                    for rid in record_ids[:5]:
                        baseline = baseline_manager.get_baseline(rid)
                        if baseline:
                            assert isinstance(baseline, BaselineRecord)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"Read thread error: {e}")
        
        write_t = threading.Thread(target=write_thread)
        read_t = threading.Thread(target=read_thread)
        
        write_t.start()
        read_t.start()
        
        write_t.join()
        read_t.join()
        
        assert len(errors) == 0, f"Thread errors occurred: {errors}"

    def test_validate_against_baseline_concurrent(self):
        """并发验证基线时应不崩溃"""
        baseline_manager = GoldenBaselineManager()
        
        for i in range(10):
            record = BaselineRecord(
                record_id=f"validation_test_{i}",
                baseline_type="test",
                data={
                    "expected_score_min": 0.5,
                    "expected_score_max": 0.9,
                },
            )
            baseline_manager.add_baseline(record)
        
        errors = []
        
        def validate_thread(thread_id):
            try:
                for i in range(10):
                    result = baseline_manager.validate_against_baseline(
                        f"validation_test_{i}",
                        {"data": {"score": 0.7}}
                    )
                    assert "passed" in result
                    assert result["passed"] is True
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=validate_thread, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors occurred: {errors}"