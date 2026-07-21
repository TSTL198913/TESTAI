import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.models.assertion import Assertion

logger = logging.getLogger("ai_test_platform")


# 1. 抽象基类
class BaseValidator(ABC):
    @abstractmethod
    def validate(self, result: Dict[str, Any], assertion: Assertion) -> bool:
        pass


# 2. 具体策略实现
class StatusValidator(BaseValidator):
    def validate(self, result: Dict[str, Any], assertion: Assertion) -> bool:
        actual = result.get("status_code")
        return str(actual) == str(assertion.expected)


class BodyContainsValidator(BaseValidator):
    def validate(self, result: Dict[str, Any], assertion: Assertion) -> bool:
        actual = str(result.get("body", ""))
        return str(assertion.expected) in actual


# 3. 引擎入口
class AssertionEngine:
    _validators: Dict[str, BaseValidator] = {
        "status_code": StatusValidator(),
        "body_contains": BodyContainsValidator(),
    }

    @classmethod
    def validate(cls, context, step_id: str, assertions: List[Assertion]) -> bool:
        result = context.results.get(step_id, {})
        passed = True

        for assertion in assertions:
            validator = cls._validators.get(assertion.check)
            if not validator:
                logger.warning(f"未知断言类型: {assertion.check}")
                continue

            if not validator.validate(result, assertion):
                logger.error(f"断言失败: {step_id} - 预期值: {assertion.expected}")
                passed = False

        result["status"] = "PASSED" if passed else "FAILED"
        return passed
