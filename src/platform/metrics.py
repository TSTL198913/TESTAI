import threading
from prometheus_client import Counter, Histogram, Gauge  # pylint: disable=import-error


class APIMetrics:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.request_counter = Counter(
            "testai_api_requests_total",
            "Total number of API requests",
            ["endpoint", "method", "status_code"],
        )

        self.request_duration = Histogram(
            "testai_api_request_duration_seconds",
            "API request duration in seconds",
            ["endpoint", "method"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )

        self.evaluate_requests = Counter(
            "testai_evaluate_requests_total",
            "Total number of AI evaluation requests",
            ["evaluation_type"],
        )

        self.evaluate_duration = Histogram(
            "testai_evaluate_duration_seconds",
            "AI evaluation duration in seconds",
            ["evaluation_type"],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )

        self.qa_requests = Counter(
            "testai_qa_requests_total",
            "Total number of QA API requests",
            [],
        )

        self.qa_duration = Histogram(
            "testai_qa_duration_seconds",
            "QA API request duration in seconds",
            [],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )

        self.classify_requests = Counter(
            "testai_classify_requests_total",
            "Total number of classification requests",
            [],
        )

        self.classify_duration = Histogram(
            "testai_classify_duration_seconds",
            "Classification request duration in seconds",
            [],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )

        self.task_status_checks = Counter(
            "testai_task_status_checks_total",
            "Total number of task status checks",
            [],
        )

        self.system_health = Gauge(
            "testai_system_health",
            "System health status (1=healthy, 0=unhealthy)",
            ["component"],
        )

        self._initialized = True

    def record_request(self, endpoint: str, method: str, status_code: int, duration: float):
        self.request_counter.labels(endpoint=endpoint, method=method, status_code=status_code).inc()
        self.request_duration.labels(endpoint=endpoint, method=method).observe(duration)

    def record_evaluate(self, evaluation_type: str, duration: float):
        self.evaluate_requests.labels(evaluation_type=evaluation_type).inc()
        self.evaluate_duration.labels(evaluation_type=evaluation_type).observe(duration)

    def record_qa(self, duration: float):
        self.qa_requests.inc()
        self.qa_duration.observe(duration)

    def record_classify(self, duration: float):
        self.classify_requests.inc()
        self.classify_duration.observe(duration)

    def record_task_status_check(self):
        self.task_status_checks.inc()

    def set_system_health(self, component: str, healthy: bool):
        self.system_health.labels(component=component).set(1 if healthy else 0)

    def record_evaluate_error(self, evaluation_type: str):
        self.evaluate_requests.labels(evaluation_type=evaluation_type).inc()
        self.evaluate_duration.labels(evaluation_type=evaluation_type).observe(0.0)