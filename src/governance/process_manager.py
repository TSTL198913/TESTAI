import os
import signal
import subprocess  # nosec B404
import threading
import shutil

TASKLIST_PATH = shutil.which("tasklist") or "tasklist"
TASKKILL_PATH = shutil.which("taskkill") or "taskkill"
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProcessInfo:
    pid: int
    command: str
    start_time: float
    timeout: Optional[float] = None
    callback: Optional[callable] = None


class ProcessManager:
    _instance = None
    _lock = threading.RLock()
    _processes: dict = {}
    _monitor_thread: Optional[threading.Thread] = None
    _running: bool = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._processes = {}
                cls._instance._monitor_thread = None
                cls._instance._running = False
            return cls._instance

    def start_monitor(self, check_interval: float = 5.0):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(check_interval,), daemon=True
        )
        self._monitor_thread.start()

    def stop_monitor(self):
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self, interval: float):
        while self._running:
            try:
                self._check_timeouts()
                self._cleanup_zombies()
            except Exception as e:
                self.logger.warning(f"Process monitor loop error: {e}")
            time.sleep(interval)

    def _check_timeouts(self):
        now = time.time()
        to_remove = []
        for pid, info in self._processes.items():
            if info.timeout and (now - info.start_time) > info.timeout:
                self.kill_process(pid)
                to_remove.append(pid)
        for pid in to_remove:
            del self._processes[pid]

    def _cleanup_zombies(self):
        to_remove = []
        for pid, info in self._processes.items():
            if not self._is_process_alive(pid):
                if info.callback:
                    try:
                        info.callback(pid)
                    except Exception as e:
                        self.logger.warning(f"Failed to execute callback for pid {pid}: {e}")
                to_remove.append(pid)
        for pid in to_remove:
            del self._processes[pid]

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
        callback: Optional[callable] = None,
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
        except Exception:
            return False

    def cleanup_all(self) -> int:
        killed = 0
        pids = list(self._processes.keys())
        for pid in pids:
            if self.kill_process(pid):
                killed += 1
        self._processes.clear()
        return killed

    def list_processes(self) -> List[ProcessInfo]:
        return list(self._processes.values())

    def get_process(self, pid: int) -> Optional[ProcessInfo]:
        return self._processes.get(pid)

    def shutdown(self):
        self.stop_monitor()
        self.cleanup_all()


process_manager = ProcessManager()
