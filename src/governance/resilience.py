import logging
import threading
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half"


class CircuitBreaker:
    def __init__(self, threshold=3, recovery_timeout=30):
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: float | None = None
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self.last_failure_time is not None and time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.failures = 0
                    self.logger.info("Circuit Breaker switching to HALF_OPEN")
                    return True
                return False
            return True

    def record_failure(self):
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.monotonic()
                self.logger.error("Circuit Breaker HALF_OPEN test failed! Returning to OPEN state.")
                return
            
            self.failures += 1
            if self.failures >= self.threshold:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.monotonic()
                self.logger.error("Circuit Breaker TRIP! Entering OPEN state.")

    def record_success(self):
        with self._lock:
            self.failures = 0
            self.state = CircuitState.CLOSED
            self.last_failure_time = None
