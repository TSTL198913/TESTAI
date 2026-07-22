import os
import threading
import time
from pathlib import Path
from typing import Optional

import portalocker


class FileLockManager:
    _instance = None
    _lock = threading.Lock()
    _active_locks: dict = {}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._active_locks = {}
        return cls._instance

    def acquire(self, file_path: str, timeout: float = 10.0) -> bool:
        normalized_path = str(Path(file_path).resolve())
        with self._lock:
            if normalized_path in self._active_locks:
                return False
            self._active_locks[normalized_path] = threading.current_thread().ident
            return True

    def release(self, file_path: str) -> bool:
        normalized_path = str(Path(file_path).resolve())
        with self._lock:
            if normalized_path in self._active_locks:
                del self._active_locks[normalized_path]
                return True
            return False

    def is_locked(self, file_path: str) -> bool:
        normalized_path = str(Path(file_path).resolve())
        with self._lock:
            return normalized_path in self._active_locks

    def get_locked_files(self) -> list:
        with self._lock:
            return list(self._active_locks.keys())


class FileLock:
    def __init__(self, file_path: str, timeout: float = 10.0):
        self._file_path = str(Path(file_path).resolve())
        self._timeout = timeout
        self._lock_manager = FileLockManager()
        self._acquired = False

    def __enter__(self):
        if not self._lock_manager.acquire(self._file_path, self._timeout):
            raise RuntimeError(f"Failed to acquire lock for {self._file_path}")
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._acquired:
            self._lock_manager.release(self._file_path)
        return False
