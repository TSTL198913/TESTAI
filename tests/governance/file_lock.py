import os
import threading
import time
from pathlib import Path
from typing import Optional


class FileLockManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._active_locks = {}

    def acquire(self, file_path: str, timeout: float = 10.0) -> bool:
        with self._lock:
            if file_path in self._active_locks:
                return False

            self._active_locks[file_path] = threading.current_thread().ident
            return True

    def release(self, file_path: str) -> bool:
        with self._lock:
            if file_path in self._active_locks:
                del self._active_locks[file_path]
                return True
            return False

    def is_locked(self, file_path: str) -> bool:
        with self._lock:
            return file_path in self._active_locks

    def get_locked_files(self) -> list:
        with self._lock:
            return list(self._active_locks.keys())


class ConcurrentFileWriter:
    _shared_lock_manager = FileLockManager()

    def __init__(self):
        self._lock_manager = ConcurrentFileWriter._shared_lock_manager

    def write_with_lock(self, file_path: str, content: str) -> tuple[bool, str]:
        file_path = str(Path(file_path).resolve())

        if not self._lock_manager.acquire(file_path):
            return False, f"File is locked: {file_path}"

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            return True, f"Write successful: {file_path}"
        except Exception as e:
            return False, f"Write failed: {str(e)}"
        finally:
            self._lock_manager.release(file_path)
