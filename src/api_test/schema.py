from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class AssertionType(str, Enum):
    STATUS_CODE = "status_code"
    JSON_PATH = "json_path"
    RESPONSE_TIME = "response_time"
    HEADER = "header"
    BODY_CONTAINS = "body_contains"


@dataclass
class APITestAssertion:
    type: AssertionType
    path: str = ""
    expected: Any = None
    operator: str = "=="


@dataclass
class APITestCase:
    name: str
    method: HTTPMethod
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    assertions: List[APITestAssertion] = field(default_factory=list)
    timeout: int = 30
    retries: int = 0


@dataclass
class APITestResult:
    test_case_name: str
    passed: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_message: str = ""
    assertion_results: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class APITestReport:
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int = 0
    avg_response_time_ms: float = 0.0
    pass_rate: float = 0.0
    results: List[APITestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)