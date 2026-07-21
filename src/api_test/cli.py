import asyncio
import argparse
from typing import List
from .test_runner import APITestRunner
from .schema import APITestCase, APITestAssertion, HTTPMethod, AssertionType


def create_test_cases() -> List[APITestCase]:
    return [
        APITestCase(
            name="health_check",
            method=HTTPMethod.GET,
            url="/health",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
                APITestAssertion(type=AssertionType.JSON_PATH, path="status", expected="healthy"),
                APITestAssertion(type=AssertionType.JSON_PATH, path="platform", expected="TestAI"),
                APITestAssertion(type=AssertionType.RESPONSE_TIME, expected=500),
            ],
        ),
        APITestCase(
            name="list_approvals",
            method=HTTPMethod.GET,
            url="/governance/approvals",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
                APITestAssertion(type=AssertionType.JSON_PATH, path="count", expected=0),
            ],
        ),
        APITestCase(
            name="get_alerts",
            method=HTTPMethod.GET,
            url="/monitoring/alerts",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
                APITestAssertion(type=AssertionType.JSON_PATH, path="count", expected=0),
            ],
        ),
        APITestCase(
            name="get_metrics",
            method=HTTPMethod.GET,
            url="/monitoring/metrics",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
            ],
        ),
        APITestCase(
            name="get_config",
            method=HTTPMethod.GET,
            url="/config",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
            ],
        ),
        APITestCase(
            name="get_dashboard_summary",
            method=HTTPMethod.GET,
            url="/dashboard/summary",
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
            ],
        ),
    ]


async def main():
    parser = argparse.ArgumentParser(description="API Test Runner")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", type=str, default=None, help="Report output path")
    args = parser.parse_args()
    
    runner = APITestRunner(args.base_url)
    test_cases = create_test_cases()
    
    print(f"Running {len(test_cases)} API tests against {args.base_url}...")
    
    report = await runner.run_test_suite(test_cases)
    
    print(f"\n{'='*60}")
    print(f"API TEST REPORT")
    print(f"{'='*60}")
    print(f"Total tests: {report.total_tests}")
    print(f"Passed: {report.passed_tests}")
    print(f"Failed: {report.failed_tests}")
    print(f"Pass rate: {report.pass_rate:.2f}%")
    print(f"Avg response time: {report.avg_response_time_ms:.2f}ms")
    
    if report.failed_tests > 0:
        print("\nFailed tests:")
        for result in report.results:
            if not result.passed:
                print(f"  ❌ {result.test_case_name}")
                if result.error_message:
                    print(f"     Error: {result.error_message}")
    
    if args.output:
        runner.generate_report(report, args.output)
        print(f"\nReport saved to {args.output}")
    else:
        print(f"\n{runner.generate_report(report)}")


if __name__ == "__main__":
    asyncio.run(main())