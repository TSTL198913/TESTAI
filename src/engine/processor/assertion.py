# src/engine/processor/assertion.py
from jsonpath_ng import parse

from src.core.exceptions import EngineError
from src.engine.processor.base import BaseProcessor
from src.models.contract import TestStep
from src.models.result import AssertionRecord, StepResult


class AssertionProcessor(BaseProcessor):
    async def _run(self, context, step: TestStep, client) -> TestStep:
        # 1. 安全获取数据并转换为模型
        result_dict = context.results.get(step.step_id)
        if result_dict is None:
            raise RuntimeError(f"Pipeline State Error: No result found for step_id: {step.step_id}")

        result = StepResult(**result_dict)

        # 2. 循环断言并记录
        for assertion in step.assertions:
            passed = True
            actual = None
            msg = None

            try:
                # 校验逻辑分发
                if assertion.check == "status_code":
                    actual = result.status_code
                    passed = (actual == assertion.expected)

                elif assertion.check == "body_contains":
                    body_str = str(result.body or "")
                    passed = (str(assertion.expected) in body_str)
                    actual = "Found" if passed else "Not Found"

                elif assertion.check == "jsonpath":
                    if not assertion.path:
                        raise ValueError("JSONPath assertion requires a 'path' field.")

                    expr = parse(assertion.path)
                    matches = expr.find(result.body)
                    actual = matches[0].value if matches else "NOT_FOUND"
                    passed = (actual == assertion.expected)

            except Exception as e:
                passed = False
                actual = f"Error: {str(e)}"
                msg = f"Exception during validation: {str(e)}"

            # 3. 压入记录 (无论成功与否)
            record = AssertionRecord(
                check=assertion.check,
                expected=assertion.expected,
                actual=actual,
                passed=passed,
                message=msg if msg else (None if passed else f"Expected {assertion.expected}, got {actual}")
            )
            # 关键修正：调用 .model_dump() 将模型实例转化为字典
            result.assertions_history.append(record.model_dump())

            # 4. 失败处理：更新状态并抛出异常
            if not passed:
                result.status = "FAILED"
                result.error = record.message
                context.results[step.step_id] = result.model_dump()
                self._raise_failure(step.step_id, assertion.check, assertion.expected, actual)

        # 5. 全部成功，更新上下文
        result.status = "PASSED"
        context.results[step.step_id] = result.model_dump()
        return step

    def _raise_failure(self, step_id, check_type, expected, actual):
        error_msg = f"Assertion Failed in {step_id} | Check: {check_type} | Expected: {expected} | Actual: {actual}"
        self.logger.error(error_msg)
        raise EngineError(error_msg)