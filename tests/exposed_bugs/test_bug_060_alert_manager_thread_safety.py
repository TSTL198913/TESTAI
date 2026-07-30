"""BUG-060: AlertManager 线程安全缺失 - 并发操作 alerts 列表无锁保护。

源码位置: src/monitoring/alert_manager.py:60-339 AlertManager

根因:
1. create_alert、acknowledge_alert、resolve_alert、list_alerts 等方法无锁保护
2. 多线程并发操作 self.alerts 列表会导致数据损坏
3. _save_alerts 和 _load_alerts 之间存在竞态条件

正确行为:
- 所有对 self.alerts 和 self.rules 的读写操作必须用锁保护
- 并发创建、确认、查询操作应线程安全
"""
import pytest
import threading
import time
import os
import tempfile
from datetime import datetime

from src.monitoring.alert_manager import AlertManager, AlertLevel, AlertType, AlertStatus


class TestAlertManagerThreadSafety:
    """AlertManager线程安全测试"""

    def test_create_alert_concurrent_thread_safe(self):
        """并发创建告警时，所有告警应正确记录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "alerts.json")
            alert_manager = AlertManager(storage_path=storage_path)
            
            alert_count = [0]
            errors = []
            
            def create_alert_thread(thread_id):
                try:
                    for i in range(10):
                        alert_manager.create_alert(
                            level=AlertLevel.WARNING,
                            alert_type=AlertType.TEST_FAILURE,
                            title=f"Thread {thread_id} Alert {i}",
                            message=f"Test alert from thread {thread_id}",
                            source="test",
                        )
                        time.sleep(0.001)
                    with threading.Lock():
                        alert_count[0] += 10
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")
            
            threads = []
            for i in range(5):
                t = threading.Thread(target=create_alert_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"Thread errors occurred: {errors}"
            assert len(alert_manager.alerts) == alert_count[0], (
                f"Expected {alert_count[0]} alerts, got {len(alert_manager.alerts)}"
            )

    def test_acknowledge_alert_concurrent_thread_safe(self):
        """并发确认告警时，所有告警应正确标记为已确认"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "alerts.json")
            alert_manager = AlertManager(storage_path=storage_path)
            
            for i in range(20):
                alert_manager.create_alert(
                    level=AlertLevel.WARNING,
                    alert_type=AlertType.TEST_FAILURE,
                    title=f"Test Alert {i}",
                    message=f"Test alert {i}",
                    source="test",
                )
            
            alert_ids = [a.alert_id for a in alert_manager.alerts]
            errors = []
            
            def acknowledge_alert_thread(thread_id):
                try:
                    start_idx = thread_id * 5
                    end_idx = start_idx + 5
                    for alert_id in alert_ids[start_idx:end_idx]:
                        result = alert_manager.acknowledge_alert(alert_id, f"user_{thread_id}")
                        assert result is not None, f"Failed to acknowledge {alert_id}"
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")
            
            threads = []
            for i in range(4):
                t = threading.Thread(target=acknowledge_alert_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"Thread errors occurred: {errors}"
            acknowledged_count = sum(1 for a in alert_manager.alerts if a.status == AlertStatus.ACKNOWLEDGED)
            assert acknowledged_count == 20, (
                f"Expected 20 acknowledged alerts, got {acknowledged_count}"
            )

    def test_list_alerts_during_concurrent_writes(self):
        """在并发写入期间查询告警列表应不崩溃"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "alerts.json")
            alert_manager = AlertManager(storage_path=storage_path)
            
            errors = []
            
            def write_thread():
                try:
                    for i in range(50):
                        alert_manager.create_alert(
                            level=AlertLevel.WARNING,
                            alert_type=AlertType.TEST_FAILURE,
                            title=f"Write Thread Alert {i}",
                            message=f"Alert from write thread",
                            source="test",
                        )
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Write thread error: {e}")
            
            def read_thread():
                try:
                    for _ in range(50):
                        result = alert_manager.list_alerts()
                        assert "alerts" in result
                        assert "total" in result
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
            assert len(alert_manager.alerts) == 50, (
                f"Expected 50 alerts, got {len(alert_manager.alerts)}"
            )