import pytest
import threading
import time
from src.security.auth import TokenManager


class TestTokenManagerRateLimitLock:
    def test_check_login_rate_limit_thread_safe(self):
        token_manager = TokenManager()
        username = "test_user"
        token_manager._login_rate_limit = 10
        token_manager._login_rate_window_seconds = 60

        results = []
        def check_rate_limit():
            for _ in range(5):
                results.append(token_manager._check_login_rate_limit(username))
                time.sleep(0.001)

        threads = [threading.Thread(target=check_rate_limit) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) >= 10, "Should allow at least 10 successful checks within limit"
        assert sum(results) <= 10, "Should not allow more than 10 successful checks within limit"