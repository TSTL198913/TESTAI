"""ProcessManager 测试 - 进程管理核心功能"""
import pytest
import subprocess
import time
import os
from unittest.mock import patch, MagicMock

from src.governance.process_manager import ProcessManager, ProcessInfo


class TestProcessManagerBasics:
    """进程管理器基础功能测试"""

    def test_singleton_pattern(self):
        """ProcessManager 必须是单例模式"""
        mgr1 = ProcessManager()
        mgr2 = ProcessManager()
        assert mgr1 is mgr2

    def test_register_and_get_process(self):
        """注册和获取进程信息"""
        mgr = ProcessManager()
        mgr._processes.clear()

        mgr.register_process(pid=1234, command="test_cmd", timeout=10.0)
        info = mgr.get_process(1234)

        assert info is not None
        assert info.pid == 1234
        assert info.command == "test_cmd"
        assert info.timeout == 10.0
        assert info.start_time > 0

    def test_list_processes(self):
        """列出所有进程"""
        mgr = ProcessManager()
        mgr._processes.clear()

        mgr.register_process(pid=1, command="cmd1")
        mgr.register_process(pid=2, command="cmd2")

        processes = mgr.list_processes()
        assert len(processes) == 2
        pids = [p.pid for p in processes]
        assert 1 in pids
        assert 2 in pids

    def test_get_nonexistent_process(self):
        """获取不存在的进程返回 None"""
        mgr = ProcessManager()
        mgr._processes.clear()

        info = mgr.get_process(9999)
        assert info is None


class TestProcessManagerMonitor:
    """进程监控测试"""

    def test_start_stop_monitor(self):
        """启动和停止监控线程"""
        mgr = ProcessManager()
        mgr._running = False
        mgr._monitor_thread = None

        mgr.start_monitor(check_interval=0.1)
        assert mgr._running is True
        assert mgr._monitor_thread is not None
        assert mgr._monitor_thread.is_alive()

        mgr.stop_monitor()
        assert mgr._running is False

    def test_monitor_already_running(self):
        """重复启动监控不会创建新线程"""
        mgr = ProcessManager()
        mgr._running = False
        mgr._monitor_thread = None

        mgr.start_monitor(check_interval=0.1)
        original_thread = mgr._monitor_thread

        mgr.start_monitor(check_interval=0.1)
        assert mgr._monitor_thread is original_thread

        mgr.stop_monitor()


class TestProcessManagerTimeout:
    """进程超时测试"""

    def test_timeout_kills_process(self):
        """超时的进程被杀死"""
        mgr = ProcessManager()
        mgr._processes.clear()

        callback_mock = MagicMock()
        mgr.register_process(
            pid=9999,
            command="test_cmd",
            timeout=0.1,
            callback=callback_mock,
        )

        time.sleep(0.2)
        mgr._check_timeouts()

        assert mgr.get_process(9999) is None

    def test_no_timeout_no_kill(self):
        """没有超时的进程不会被杀死"""
        mgr = ProcessManager()
        mgr._processes.clear()

        mgr.register_process(pid=9999, command="test_cmd", timeout=None)

        mgr._check_timeouts()

        assert mgr.get_process(9999) is not None


class TestProcessManagerCleanup:
    """进程清理测试"""

    def test_cleanup_zombies(self):
        """清理已结束的进程"""
        mgr = ProcessManager()
        mgr._processes.clear()

        callback_mock = MagicMock()
        mgr.register_process(
            pid=999999,
            command="zombie_cmd",
            callback=callback_mock,
        )

        with patch.object(mgr, '_is_process_alive', return_value=False):
            mgr._cleanup_zombies()

        assert mgr.get_process(999999) is None
        callback_mock.assert_called_once_with(999999)

    def test_cleanup_all(self):
        """清理所有进程"""
        mgr = ProcessManager()
        mgr._processes.clear()

        mgr.register_process(pid=1, command="cmd1")
        mgr.register_process(pid=2, command="cmd2")

        with patch.object(mgr, 'kill_process', return_value=True):
            killed = mgr.cleanup_all()

        assert killed == 2
        assert len(mgr._processes) == 0

    def test_shutdown(self):
        """关闭进程管理器"""
        mgr = ProcessManager()
        mgr._running = False
        mgr._monitor_thread = None

        mgr.start_monitor(check_interval=0.1)
        mgr.register_process(pid=1, command="cmd1")

        with patch.object(mgr, 'kill_process', return_value=True):
            mgr.shutdown()

        assert mgr._running is False
        assert len(mgr._processes) == 0


class TestProcessManagerPlatform:
    """平台相关测试"""

    def test_is_process_alive_windows(self):
        """Windows 平台进程存活检测"""
        mgr = ProcessManager()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "1234"
            result = mgr._is_process_alive(1234)
            assert result is True

            mock_run.return_value.stdout = ""
            result = mgr._is_process_alive(1234)
            assert result is False

    def test_kill_process_windows(self):
        """Windows 平台进程杀死"""
        mgr = ProcessManager()

        with patch('subprocess.run') as mock_run:
            result = mgr.kill_process(1234)
            assert result is True
            mock_run.assert_called_once()

        with patch('subprocess.run', side_effect=OSError("kill failed")):
            result = mgr.kill_process(1234)
            assert result is False