import pytest
import threading
from src.security.auth import TokenManager


class TestTokenManagerLoginRateLimitThreadSafe:
    def test_login_rate_limit_is_thread_safe(self):
        tm = TokenManager(secret_key="test_secret_key_32_bytes_long_secure_")
        
        results = []
        username = "test_user"
        
        def login_attempt():
            try:
                result = tm.authenticate(username, "wrong_password")
                results.append(result)
            except Exception as e:
                results.append(f"error: {e}")
        
        threads = [threading.Thread(target=login_attempt) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        failed_attempts = sum(1 for r in results if r is None)
        rate_limit_info = tm.get_rate_limit_info(username)
        
        assert failed_attempts >= 5, f"Expected at least 5 failed attempts due to rate limiting, got {failed_attempts}"
        assert rate_limit_info["remaining"] == 0, f"Expected 0 remaining attempts, got {rate_limit_info['remaining']}"