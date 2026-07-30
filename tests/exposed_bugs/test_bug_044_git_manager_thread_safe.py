import pytest
import threading
from unittest.mock import patch, MagicMock
from src.governance.git_manager import GitTransactionManager


class TestGitManagerThreadSafe:
    def test_start_transaction_is_thread_safe(self):
        git_mgr = GitTransactionManager(repo_path=".")
        
        results = []
        
        def start_tx_thread(tx_id):
            try:
                git_mgr.start_transaction(tx_id)
                results.append(True)
            except Exception as e:
                results.append(f"error: {e}")
        
        threads = [threading.Thread(target=start_tx_thread, args=(f"tx_{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert all(r is True for r in results), f"Thread safety issue: {results}"