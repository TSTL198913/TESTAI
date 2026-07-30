import pytest
from src.governance.resilience import CircuitBreaker, CircuitState


class TestCircuitBreakerHalfOpenFailure:
    def test_half_open_failure_returns_to_open(self):
        breaker = CircuitBreaker(threshold=3, recovery_timeout=1)
        
        breaker.state = CircuitState.HALF_OPEN
        breaker.failures = 0
        
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN, \
            "CircuitBreaker should transition back to OPEN when HALF_OPEN test call fails"

    def test_closed_state_allows_execution(self):
        breaker = CircuitBreaker(threshold=3, recovery_timeout=30)
        
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.CLOSED

    def test_open_state_blocks_execution(self):
        breaker = CircuitBreaker(threshold=3, recovery_timeout=30)
        
        breaker.state = CircuitState.OPEN
        breaker.last_failure_time = float('inf')
        
        assert breaker.can_execute() is False