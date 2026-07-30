import pytest
import threading
import tempfile
import os
import json
from src.governance.baseline import GoldenBaselineManager, BaselineRecord


class TestGoldenBaselineManagerLogger:
    def test_logger_is_initialized(self):
        GoldenBaselineManager._instance = None
        
        manager = GoldenBaselineManager()
        assert hasattr(manager, '_logger') or hasattr(manager, 'logger'), \
            "GoldenBaselineManager should have a logger attribute"

    def test_add_baseline_thread_safe(self):
        GoldenBaselineManager._instance = None
        
        manager = GoldenBaselineManager()
        original_count = len(manager.get_all_baseline_ids())
        
        results = []
        
        def add_baseline_thread(i):
            try:
                record = BaselineRecord(
                    record_id=f"thread_test_{i}",
                    baseline_type="test",
                    data={"name": f"test_{i}"},
                )
                manager.add_baseline(record)
                results.append(True)
            except Exception as e:
                results.append(f"error: {e}")
        
        threads = [threading.Thread(target=add_baseline_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert all(r is True for r in results), f"Thread safety issue: {results}"
        assert len(manager.get_all_baseline_ids()) == original_count + 10