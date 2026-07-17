# src/report/storage.py
import threading

class Registry:
    def __init__(self):
        self._results = {}
        self._lock = threading.Lock()

    def update(self, case_id, result):
        with self._lock:
            self._results[case_id] = result

    def get_all(self):
        with self._lock:
            return dict(self._results)

registry = Registry()