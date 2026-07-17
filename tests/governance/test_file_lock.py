import os
import threading
import time
from pathlib import Path

import pytest

from tests.governance.file_lock import ConcurrentFileWriter, FileLockManager


class TestFileLockManager:
    def test_acquire_lock(self):
        manager = FileLockManager()
        result = manager.acquire("test_file.txt")
        assert result is True
        assert manager.is_locked("test_file.txt") is True

    def test_acquire_locked_file_returns_false(self):
        manager = FileLockManager()
        manager.acquire("test_file.txt")
        result = manager.acquire("test_file.txt")
        assert result is False

    def test_release_lock(self):
        manager = FileLockManager()
        manager.acquire("test_file.txt")
        result = manager.release("test_file.txt")
        assert result is True
        assert manager.is_locked("test_file.txt") is False

    def test_release_unlocked_file_returns_false(self):
        manager = FileLockManager()
        result = manager.release("test_file.txt")
        assert result is False

    def test_is_locked(self):
        manager = FileLockManager()
        assert manager.is_locked("test_file.txt") is False
        manager.acquire("test_file.txt")
        assert manager.is_locked("test_file.txt") is True
        manager.release("test_file.txt")
        assert manager.is_locked("test_file.txt") is False

    def test_get_locked_files(self):
        manager = FileLockManager()
        assert len(manager.get_locked_files()) == 0

        manager.acquire("file1.txt")
        manager.acquire("file2.txt")

        locked = manager.get_locked_files()
        assert len(locked) == 2
        assert "file1.txt" in locked
        assert "file2.txt" in locked


class TestConcurrentFileWriter:
    def test_write_with_lock(self, tmp_path):
        writer = ConcurrentFileWriter()
        test_file = tmp_path / "test_write.txt"

        success, msg = writer.write_with_lock(str(test_file), "test content")
        assert success is True
        assert "Write successful" in msg
        assert test_file.read_text() == "test content"

    def test_concurrent_writes_are_serialized(self, tmp_path):
        writer = ConcurrentFileWriter()
        test_file = tmp_path / "concurrent.txt"
        results = []

        def writer_thread(thread_id):
            for i in range(5):
                success = False
                attempts = 0
                while not success and attempts < 10:
                    success, msg = writer.write_with_lock(
                        str(test_file), f"thread{thread_id}_write{i}\n"
                    )
                    if not success:
                        time.sleep(0.01)
                        attempts += 1
                results.append((thread_id, success))

        threads = []
        for i in range(3):
            t = threading.Thread(target=writer_thread, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        content = test_file.read_text()
        lines = content.strip().split('\n')
        assert len(lines) == 15

    def test_write_fails_when_locked(self, tmp_path):
        writer1 = ConcurrentFileWriter()
        writer2 = ConcurrentFileWriter()
        test_file = tmp_path / "locked.txt"

        writer1._lock_manager.acquire(str(test_file))

        success, msg = writer2.write_with_lock(str(test_file), "should fail")
        assert success is False
        assert "File is locked" in msg

        writer1._lock_manager.release(str(test_file))

    def test_multiple_files_can_be_locked_independently(self, tmp_path):
        manager = FileLockManager()
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        assert manager.acquire(str(file1)) is True
        assert manager.acquire(str(file2)) is True

        assert manager.is_locked(str(file1)) is True
        assert manager.is_locked(str(file2)) is True

        assert manager.acquire(str(file1)) is False

        manager.release(str(file1))
        assert manager.acquire(str(file1)) is True