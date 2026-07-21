import json
import os
from typing import List, Dict, Any
from datetime import datetime
from .client import APITestClient
from .schema import APITestCase, APITestResult, APITestReport, AssertionType


class APITestRunner:
    def __init__(self, base_url: str):
        self.client = APITestClient(base_url)

    def _evaluate_assertion(
        self, assertion: AssertionType, path: str, expected: Any, actual: Any, operator: str = "=="
    ) -> bool:
        if assertion == AssertionType.STATUS_CODE:
            return actual == expected
        elif assertion == AssertionType.RESPONSE_TIME:
            return actual <= expected
        elif assertion == AssertionType.BODY_CONTAINS:
            return expected in str(actual)
        elif assertion == AssertionType.JSON_PATH:
            return self._evaluate_json_path(path, actual, expected, operator)
        elif assertion == AssertionType.HEADER:
            return actual == expected
        return False

    def _evaluate_json_path(self, path: str, data: Dict[str, Any], expected: Any, operator: str) -> bool:
        value = data
        for key in path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit():
                idx = int(key)
                if idx < len(value):
                    value = value[idx]
                else:
                    return False
            else:
                return False
        
        if operator == "==":
            return value == expected
        elif operator == "!=":
            return value != expected
        elif operator == ">":
            return value > expected
        elif operator == "<":
            return value < expected
        elif operator == ">=":
            return value >= expected
        elif operator == "<=":
            return value <= expected
        elif operator == "contains":
            return expected in str(value)
        return False

    async def run_test_case(self, test_case: APITestCase) -> APITestResult:
        assertion_results = []
        passed = True
        error_message = ""
        
        try:
            status_code, response_body, response_time, headers = await self.client.send_request(
                method=test_case.method,
                url=test_case.url,
                headers=test_case.headers,
                params=test_case.params,
                body=test_case.body,
            )
            
            for assertion in test_case.assertions:
                actual_value = None
                
                if assertion.type == AssertionType.STATUS_CODE:
                    actual_value = status_code
                elif assertion.type == AssertionType.RESPONSE_TIME:
                    actual_value = response_time
                elif assertion.type == AssertionType.BODY_CONTAINS:
                    actual_value = response_body
                elif assertion.type == AssertionType.JSON_PATH:
                    actual_value = response_body
                elif assertion.type == AssertionType.HEADER:
                    actual_value = headers.get(assertion.path, "")
                
                assertion_passed = self._evaluate_assertion(
                    assertion.type, assertion.path, assertion.expected, actual_value, assertion.operator
                )
                
                assertion_results.append({
                    "type": assertion.type.value,
                    "path": assertion.path,
                    "expected": assertion.expected,
                    "actual": actual_value,
                    "operator": assertion.operator,
                    "passed": assertion_passed,
                })
                
                if not assertion_passed:
                    passed = False
            
        except Exception as e:
            passed = False
            error_message = str(e)
        
        return APITestResult(
            test_case_name=test_case.name,
            passed=passed,
            status_code=status_code if 'status_code' in dir() else None,
            response_time_ms=response_time if 'response_time' in dir() else None,
            error_message=error_message,
            assertion_results=assertion_results,
        )

    async def run_test_suite(self, test_cases: List[APITestCase]) -> APITestReport:
        start_time = datetime.now()
        results = []
        passed_count = 0
        total_time_ms = 0.0
        
        for test_case in test_cases:
            result = await self.run_test_case(test_case)
            results.append(result)
            if result.passed:
                passed_count += 1
            if result.response_time_ms:
                total_time_ms += result.response_time_ms
        
        end_time = datetime.now()
        total_tests = len(test_cases)
        avg_response_time = total_time_ms / total_tests if total_tests > 0 else 0.0
        pass_rate = (passed_count / total_tests) * 100 if total_tests > 0 else 0.0
        
        await self.client.close()
        
        return APITestReport(
            total_tests=total_tests,
            passed_tests=passed_count,
            failed_tests=total_tests - passed_count,
            avg_response_time_ms=avg_response_time,
            pass_rate=pass_rate,
            results=results,
            start_time=start_time,
            end_time=end_time,
        )

    def generate_report(self, report: APITestReport, output_path: str = None) -> str:
        report_dict = {
            "summary": {
                "total_tests": report.total_tests,
                "passed_tests": report.passed_tests,
                "failed_tests": report.failed_tests,
                "pass_rate": f"{report.pass_rate:.2f}%",
                "avg_response_time_ms": f"{report.avg_response_time_ms:.2f}",
                "start_time": report.start_time.isoformat(),
                "end_time": report.end_time.isoformat(),
            },
            "details": [
                {
                    "test_name": r.test_case_name,
                    "passed": r.passed,
                    "status_code": r.status_code,
                    "response_time_ms": r.response_time_ms,
                    "error": r.error_message,
                    "assertions": r.assertion_results,
                }
                for r in report.results
            ],
        }
        
        report_json = json.dumps(report_dict, indent=2, ensure_ascii=False)
        
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_json)
        
        return report_json