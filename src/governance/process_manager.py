import os
import signal
import subprocess  # nosec B404
import threading
import shutil

TASKLIST_PATH = shutil.which("tasklist") or "tasklist"
TASKKILL_PATH = shutil.which("taskkill") or "taskkill"
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable

@dataclass
class ProcessInfo:
    pid: int
    command: str
    start_time: float
    timeout: Optional[float] = None
    callback: Optional[Callable] = None


class ProcessManager:
    _instance = None
    _lock = threading.RLock()
    _processes: dict = {}
    _monitor_thread: Optional[threading.Thread] = None
    _running: bool = False
    logger = logging.getLogger("ProcessManager")

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._processes = {}
                cls._instance._monitor_thread = None
                cls._instance._running = False
            return cls._instance

    def start_monitor(self, check_interval: float = 5.0):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, args=(check_interval,), daemon=True
            )
            self._monitor_thread.start()

    def stop_monitor(self):
        with self._lock:
            self._running = False
            monitor = self._monitor_thread
        if monitor:
            monitor.join(timeout=5)

    def _monitor_loop(self, interval: float):
        # P5 修复: 捕获具体异常 (OSError/subprocess.SubprocessError/RuntimeError),
        # 禁止裸 except Exception 吞没监控真实失败; 非预期异常 (编程错误) 向上传播。
        while self._running:
            try:
                self._check_timeouts()
                self._cleanup_zombies()
            except (OSError, subprocess.SubprocessError, RuntimeError) as e:
                self.logger.warning(
                    "Process monitor loop error: %s (type=%s)",
                    e, type(e).__name__,
                    exc_info=True,
                )
            time.sleep(interval)

    def _check_timeouts(self):
        now = time.time()
        # P5 修复: 持锁快照迭代, 避免并发 register_process 修改字典触发
        # RuntimeError: dictionary changed size during iteration。
        with self._lock:
            timed_out = [
                pid for pid, info in self._processes.items()
                if info.timeout and (now - info.start_time) > info.timeout
            ]
        # kill_process 可能阻塞 (subprocess 调用), 在锁外执行避免长时间持锁
        for pid in timed_out:
            self.kill_process(pid)
        if timed_out:
            with self._lock:
                for pid in timed_out:
                    self._processes.pop(pid, None)

    def _cleanup_zombies(self):
        # P5 修复: 持锁快照迭代, 避免并发修改触发 RuntimeError。
        with self._lock:
            snapshot = list(self._processes.items())
        to_remove = []
        for pid, info in snapshot:
            if not self._is_process_alive(pid):
                if info.callback:
                    # 回调为用户传入的任意 Callable, 可能抛任意异常;
                    # 捕获 Exception 并结构化日志, 避免单个回调崩溃拖垮监控线程。
                    try:
                        info.callback(pid)
                    except Exception as e:
                        self.logger.warning(
                            "Failed to execute callback for pid %s: %s (type=%s)",
                            pid, e, type(e).__name__,
                            exc_info=True,
                        )
                to_remove.append(pid)
        if to_remove:
            with self._lock:
                for pid in to_remove:
                    self._processes.pop(pid, None)

    def _is_process_alive(self, pid: int) -> bool:
        try:
            if os.name == "nt":
                result = subprocess.run(
                    [TASKLIST_PATH, "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                )  # nosec B603
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.CalledProcessError):
            return False

    def register_process(
        self,
        pid: int,
        command: str,
        timeout: Optional[float] = None,
        callback: Optional[Callable] = None,
    ):
        with self._lock:
            self._processes[pid] = ProcessInfo(
                pid=pid,
                command=command,
                start_time=time.time(),
                timeout=timeout,
                callback=callback,
            )

    def kill_process(self, pid: int) -> bool:
        # P5 修复: 捕获具体异常 (OSError, subprocess.SubprocessError),
        # 禁止裸 except Exception 吞没; 失败输出结构化日志 (规则1)。
        # 非预期异常 (编程错误) 向上传播, 不静默吞没。
        try:
            if os.name == "nt":
                subprocess.run(
                    [TASKKILL_PATH, "/F", "/T", "/PID", str(pid)], capture_output=True
                )  # nosec B603
            else:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if self._is_process_alive(pid):
                    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
                    os.kill(pid, kill_signal)
            return True
        except (OSError, subprocess.SubprocessError) as e:
            self.logger.warning(
                "kill_process failed for pid %s: %s (type=%s)",
                pid, e, type(e).__name__,
                exc_info=True,
            )
            return False

    def cleanup_all(self) -> int:
        # P5 修复: 持锁快照, 锁外 kill (避免阻塞其他操作), 持锁清空。
        with self._lock:
            pids = list(self._processes.keys())
        killed = 0
        for pid in pids:
            if self.kill_process(pid):
                killed += 1
        with self._lock:
            self._processes.clear()
        return killed

    def list_processes(self) -> List[ProcessInfo]:
        # P5 修复: 持锁快照, 避免并发修改触发 RuntimeError。
        with self._lock:
            return list(self._processes.values())

    def get_process(self, pid: int) -> Optional[ProcessInfo]:
        # P5 修复: 持锁读取, 避免并发 clear 返回脏数据。
        with self._lock:
            return self._processes.get(pid)

    def shutdown(self):
        self.stop_monitor()
        self.cleanup_all()


process_manager = ProcessManager()
