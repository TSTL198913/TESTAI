# src/models/result.py
from pydantic import BaseModel
from typing import Any, Optional, List


class AssertionRecord(BaseModel):
    check: str
    expected: Any
    actual: Any
    passed: bool
    message: Optional[str] = None

class StepResult(BaseModel):
    status: str  # "PASSED" or "FAILED"
    status_code: Optional[int] = None
    body: Any = None
    assertions_history: List[dict] = []  # 新增：存储该步骤下所有断言的结果
    error: Optional[str] = None