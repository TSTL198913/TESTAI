"""P5 并发安全测试: process_manager 锁外迭代与裸异常吞没

业务规则 (规则1 可信代码 + 异常处理规范):
- _check_timeouts / _cleanup_zombies 迭代 self._processes 时必须持有 _lock,
  否则并发 register_process 修改字典会触发
  'RuntimeError: dictionary changed size during iteration', 监控线程崩溃。
- kill_process 禁止裸 except Exception / except: 吞没异常,
  必须捕获具体异常 (OSError, subprocess.SubprocessError, ValueError)
  并输出带上下文的结构化日志。
- cleanup_all / list_processes / get_process 读写共享字典必须持锁。

关联缺陷: P5-1 process_manager 并发不安全
"""
import ast
import inspect
import subprocess
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pytest

from src.governance.process_manager import ProcessManager, ProcessInfo


def _reset_singleton():
    mgr = ProcessManager()
    mgr._processes.clear()
    mgr._running = False
    mgr._monitor_thread = None


def _method_src(method) -> str:
    """获取方法源码并去除缩进, 便于 ast.parse。"""
    return textwrap.dedent(inspect.getsource(method))


def _has_lock_with(tree: ast.AST, lock_attr: str = "self._lock") -> bool:
    """检测 AST 中是否存在 with self._lock: 语句。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                try:
                    ctx = ast.unparse(item.context_expr)
                except Exception:
                    continue
                if lock_attr in ctx:
                    return True
    return False


def _bare_excepts(tree: ast.AST) -> list:
    """收集裸 except: 与 except Exception: 节点描述。"""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                found.append("bare except:")
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                found.append("except Exception:")
    return found


# ---------------------------------------------------------------------------
# 一、静态结构校验 (确定性): 确保迭代持锁 + 无裸异常
# ---------------------------------------------------------------------------
class TestProcessManagerSourceStructure:
    """静态结构校验: 迭代持锁 + 无裸异常 (确定性, 当前应失败)"""

    def test_check_timeouts_iterates_under_lock(self):
        """正向: _check_timeouts 必须在 with self._lock 内快照迭代。

        不持锁迭代 self._processes.items() 时, 若另一线程 register_process
        修改字典, CPython 会抛 RuntimeError: dictionary changed size during
        iteration, 导致监控线程崩溃。
        """
        tree = ast.parse(_method_src(ProcessManager._check_timeouts))
        assert _has_lock_with(tree), (
            "_check_timeouts 未在 self._lock 保护下迭代 self._processes, "
            "并发 register_process 会触发 RuntimeError: dictionary changed "
            "size during iteration, 监控线程崩溃"
        )

    def test_cleanup_zombies_iterates_under_lock(self):
        """正向: _cleanup_zombies 必须在 with self._lock 内快照迭代。"""
        tree = ast.parse(_method_src(ProcessManager._cleanup_zombies))
        assert _has_lock_with(tree), (
            "_cleanup_zombies 未在 self._lock 保护下迭代 self._processes, "
            "并发修改会触发 RuntimeError"
        )

    def test_cleanup_all_under_lock(self):
        """正向: cleanup_all 读键/清空必须在锁内。"""
        tree = ast.parse(_method_src(ProcessManager.cleanup_all))
        assert _has_lock_with(tree), (
            "cleanup_all 未在 self._lock 保护下读写 self._processes, "
            "并发 register 会导致漏杀或双杀"
        )

    def test_list_processes_under_lock(self):
        """正向: list_processes 必须持锁快照。"""
        tree = ast.parse(_method_src(ProcessManager.list_processes))
        assert _has_lock_with(tree), (
            "list_processes 未持锁读取 self._processes.values(), "
            "并发修改会触发 RuntimeError"
        )

    def test_get_process_under_lock(self):
        """正向: get_process 必须持锁读取。"""
        tree = ast.parse(_method_src(ProcessManager.get_process))
        assert _has_lock_with(tree), (
            "get_process 未持锁读取 self._processes, 并发 clear 可能返回脏数据"
        )

    def test_kill_process_no_bare_exception(self):
        """负向: kill_process 禁止裸 except Exception / except: 吞没异常。

        违反异常处理规范: 必须捕获具体异常
        (OSError, subprocess.SubprocessError, ValueError)。
        """
        tree = ast.parse(_method_src(ProcessManager.kill_process))
        bare = _bare_excepts(tree)
        assert not bare, (
            f"kill_process 存在裸异常吞没: {bare}, 违反异常处理规范: "
            "必须捕获具体异常 (OSError, subprocess.SubprocessError)"
        )

    def test_monitor_loop_no_bare_exception(self):
        """负向: _monitor_loop 禁止裸 except Exception 吞没监控异常。

        监控循环吞没异常会掩盖 _check_timeouts/_cleanup_zombies 的真实失败。
        """
        tree = ast.parse(_method_src(ProcessManager._monitor_loop))
        bare = _bare_excepts(tree)
        assert not bare, (
            f"_monitor_loop 存在裸异常吞没: {bare}, 会掩盖监控真实失败"
        )


# ---------------------------------------------------------------------------
# 二、功能并发测试 (行为): 并发不崩 + 一致性
# ---------------------------------------------------------------------------
class TestProcessManagerConcurrency:
    """功能并发测试: 并发读写不触发 RuntimeError 且保持一致性"""

    def test_concurrent_register_and_check_timeouts_no_crash(self):
        """正向: 并发 register_process + _check_timeouts 不抛 RuntimeError。

        场景: 多线程持续 register/unregister, 同时反复调用 _check_timeouts。
        修复前: 锁外迭代会被并发修改打断 -> RuntimeError。
        """
        _reset_singleton()
        mgr = ProcessManager()
        errors = []
        stop = threading.Event()

        def registrar():
            i = 0
            while not stop.is_set():
                try:
                    mgr.register_process(pid=10000 + i, command=f"cmd{i}", timeout=None)
                    # 模拟生命周期: 立即移除制造高频修改
                    with mgr._lock:
                        mgr._processes.pop(10000 + i, None)
                    i += 1
                except Exception as e:
                    errors.append(e)
                    return
            errors.append("registrar-done")

        def timeout_checker():
            for _ in range(200):
                try:
                    mgr._check_timeouts()
                except RuntimeError as e:
                    errors.append(e)
                    return
                except Exception as e:
                    errors.append(e)
                    return
            errors.append("checker-done")

        threads = [threading.Thread(target=registrar) for _ in range(4)]
        threads += [threading.Thread(target=timeout_checker) for _ in range(4)]
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join(timeout=5)

        runtime_errors = [e for e in errors if isinstance(e, RuntimeError)]
        assert not runtime_errors, (
            f"并发 register + _check_timeouts 触发 RuntimeError: {runtime_errors}"
        )

    def test_concurrent_register_and_cleanup_zombies_no_crash(self):
        """正向: 并发 register + _cleanup_zombies 不抛 RuntimeError。"""
        _reset_singleton()
        mgr = ProcessManager()
        errors = []
        stop = threading.Event()

        # 让 _is_process_alive 始终返回 False 以触发清理路径
        mgr._is_process_alive = lambda pid: False

        def registrar():
            i = 0
            while not stop.is_set():
                try:
                    mgr.register_process(pid=20000 + i, command=f"z{i}")
                    i += 1
                except Exception as e:
                    errors.append(e)
                    return
            errors.append("registrar-done")

        def cleaner():
            for _ in range(200):
                try:
                    mgr._cleanup_zombies()
                except RuntimeError as e:
                    errors.append(e)
                    return
                except Exception as e:
                    errors.append(e)
                    return
            errors.append("cleaner-done")

        threads = [threading.Thread(target=registrar) for _ in range(4)]
        threads += [threading.Thread(target=cleaner) for _ in range(4)]
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join(timeout=5)

        runtime_errors = [e for e in errors if isinstance(e, RuntimeError)]
        assert not runtime_errors, (
            f"并发 register + _cleanup_zombies 触发 RuntimeError: {runtime_errors}"
        )

    def test_concurrent_list_processes_consistent(self):
        """正向: 并发 register + list_processes 返回有效快照, 不崩。"""
        _reset_singleton()
        mgr = ProcessManager()
        errors = []
        stop = threading.Event()

        def registrar():
            for i in range(500):
                try:
                    mgr.register_process(pid=30000 + i, command=f"c{i}")
                except Exception as e:
                    errors.append(e)
                    return

        def lister():
            while not stop.is_set():
                try:
                    procs = mgr.list_processes()
                    # 快照必须全部为 ProcessInfo 实例
                    for p in procs:
                        assert isinstance(p, ProcessInfo), f"脏数据: {p}"
                except RuntimeError as e:
                    errors.append(e)
                    return
                except Exception as e:
                    errors.append(e)
                    return

        t_reg = threading.Thread(target=registrar)
        t_list = [threading.Thread(target=lister) for _ in range(3)]
        t_reg.start()
        for t in t_list:
            t.start()
        t_reg.join(timeout=5)
        stop.set()
        for t in t_list:
            t.join(timeout=5)

        runtime_errors = [e for e in errors if isinstance(e, RuntimeError)]
        assert not runtime_errors, (
            f"并发 list_processes 触发 RuntimeError: {runtime_errors}"
        )

    def test_concurrent_cleanup_all_no_double_kill(self):
        """正向: 并发 cleanup_all 不漏杀/双杀, killed <= 注册数。"""
        _reset_singleton()
        mgr = ProcessManager()
        for i in range(100):
            mgr.register_process(pid=40000 + i, command=f"k{i}")

        kill_calls = []
        original_kill = mgr.kill_process

        def counting_kill(pid):
            kill_calls.append(pid)
            return True

        mgr.kill_process = counting_kill
        killed_results = []

        def cleanup_worker():
            killed_results.append(mgr.cleanup_all())

        threads = [threading.Thread(target=cleanup_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        total_killed = sum(killed_results)
        # 100 个进程, 并发 cleanup 不应超过 100 (双杀) 也不应为负
        assert total_killed <= 100, (
            f"并发 cleanup_all 双杀: 总 killed={total_killed} > 注册数 100"
        )
        mgr.kill_process = original_kill


# ---------------------------------------------------------------------------
# 三、异常处理测试: kill_process 捕获具体异常
# ---------------------------------------------------------------------------
class TestProcessManagerKillExceptions:
    """异常场景: kill_process 必须捕获具体异常而非裸 except"""

    def test_kill_process_handles_oserror(self):
        """异常: kill_process 捕获 OSError 返回 False, 不向上抛。"""
        _reset_singleton()
        mgr = ProcessManager()

        with patch("subprocess.run", side_effect=OSError("no such process")):
            result = mgr.kill_process(8888)
        assert result is False, "OSError 应返回 False 而非抛出"

    def test_kill_process_handles_subprocess_error(self):
        """异常: kill_process 捕获 subprocess.SubprocessError 返回 False。"""
        _reset_singleton()
        mgr = ProcessManager()

        with patch("subprocess.run", side_effect=subprocess.SubprocessError("fail")):
            result = mgr.kill_process(8888)
        assert result is False, "SubprocessError 应返回 False 而非抛出"

    def test_kill_process_does_not_swallow_unexpected_exception(self):
        """异常: kill_process 不得吞没非预期异常 (如 KeyboardInterrupt)。

        裸 except Exception 会吞掉 KeyboardInterrupt? 不会 (KeyboardInterrupt
        继承 BaseException)。但裸 except: 会。这里验证 RuntimeError 等非
        IO 异常不被静默吞没 —— 修复后应只捕获具体异常。
        """
        _reset_singleton()
        mgr = ProcessManager()

        # ValueError 不在 kill_process 的合理异常集内;
        # 修复后若只捕获 OSError/SubprocessError, ValueError 应向上传播
        with patch("subprocess.run", side_effect=ValueError("unexpected")):
            with pytest.raises(ValueError):
                mgr.kill_process(8888)

    def test_kill_process_logs_on_failure(self):
        """异常: kill_process 失败时必须输出结构化日志 (规则1)。"""
        _reset_singleton()
        mgr = ProcessManager()

        with patch("subprocess.run", side_effect=OSError("boom")):
            with patch.object(mgr.logger, "warning") as mock_warn:
                mgr.kill_process(8888)
        # 修复后应在失败路径记录日志
        assert mock_warn.called, (
            "kill_process 失败未输出日志, 违反规则1 (结构化日志要求)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
