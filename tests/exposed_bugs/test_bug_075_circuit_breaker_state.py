import pytest
import threading
import time
from src.governance.resilience import CircuitBreaker, CircuitState


class TestCircuitBreakerState:
    def test_record_success_resets_failure_time(self):
        breaker = CircuitBreaker(threshold=1, recovery_timeout=1)
        
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.last_failure_time is not None
        
        time.sleep(1.5)
        
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0
        
        assert breaker.last_failure_time is None, \
            f"last_failure_time should be reset to None after success, got {breaker.last_failure_time}"

    def test_record_success_called_in_closed_state(self):
        breaker = CircuitBreaker(threshold=3, recovery_timeout=10)
        
        breaker.record_success()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0
        assert breaker.last_failure_time is None