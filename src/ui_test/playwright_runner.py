import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class PlaywrightAction(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    WAIT = "wait"
    ASSERT = "assert"
    SCROLL = "scroll"
    HOVER = "hover"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    FILL = "fill"
    CLEAR = "clear"


class AssertionOperator(str, Enum):
    EQUALS = "=="
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"


@dataclass
class PlaywrightStep:
    action: PlaywrightAction
    selector: str = ""
    value: str = ""
    wait_time_ms: int = 0
    assertion_operator: AssertionOperator = AssertionOperator.EQUALS


@dataclass
class PlaywrightTestCase:
    id: str
    name: str
    description: str = ""
    browser: BrowserType = BrowserType.CHROMIUM
    viewport_width: int = 1920
    viewport_height: int = 1080
    steps: List[PlaywrightStep] = field(default_factory=list)
    base_url: str = ""
    timeout_ms: int = 30000


@dataclass
class PlaywrightTestResult:
    test_case_id: str
    test_case_name: str
    passed: bool
    duration_ms: int = 0
    error_message: str = ""
    screenshot_path: str = ""
    logs: List[str] = field(default_factory=list)


@dataclass
class PlaywrightTestReport:
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration_ms: int = 0
    results: List[PlaywrightTestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)


class PlaywrightRunner:
    def __init__(self, browser_type: BrowserType = BrowserType.CHROMIUM, headless: bool = True):
        self.browser_type = browser_type
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._playwright_available = self._check_playwright()

    def _check_playwright(self) -> bool:
        try:
            import playwright
            return True
        except ImportError:
            return False

    async def _setup_browser(self):
        if not self._playwright_available:
            raise ImportError("Playwright is not installed. Please install with: pip install playwright")

        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()

        browser_cls = {
            BrowserType.CHROMIUM: playwright.chromium,
            BrowserType.FIREFOX: playwright.firefox,
            BrowserType.WEBKIT: playwright.webkit,
        }[self.browser_type]

        self.browser = await browser_cls.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def _teardown_browser(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def _execute_step(self, step: PlaywrightStep) -> Dict[str, Any]:
        if not self.page:
            return {"success": False, "error": "Page not initialized"}

        try:
            if step.action == PlaywrightAction.NAVIGATE:
                url = step.value
                if step.base_url and not url.startswith("http"):
                    url = step.base_url + url
                await self.page.goto(url, wait_until="domcontentloaded")
                return {"success": True}

            elif step.action == PlaywrightAction.CLICK:
                await self.page.click(step.selector)
                return {"success": True}

            elif step.action == PlaywrightAction.TYPE:
                await self.page.type(step.selector, step.value)
                return {"success": True}

            elif step.action == PlaywrightAction.FILL:
                await self.page.fill(step.selector, step.value)
                return {"success": True}

            elif step.action == PlaywrightAction.CLEAR:
                await self.page.clear(step.selector)
                return {"success": True}

            elif step.action == PlaywrightAction.WAIT:
                if step.wait_time_ms > 0:
                    await self.page.wait_for_timeout(step.wait_time_ms)
                else:
                    await self.page.wait_for_load_state("networkidle")
                return {"success": True}

            elif step.action == PlaywrightAction.SCROLL:
                await self.page.evaluate(f"document.querySelector('{step.selector}')?.scrollIntoView()")
                return {"success": True}

            elif step.action == PlaywrightAction.HOVER:
                await self.page.hover(step.selector)
                return {"success": True}

            elif step.action == PlaywrightAction.SELECT:
                await self.page.select_option(step.selector, step.value)
                return {"success": True}

            elif step.action == PlaywrightAction.CHECK:
                await self.page.check(step.selector)
                return {"success": True}

            elif step.action == PlaywrightAction.UNCHECK:
                await self.page.uncheck(step.selector)
                return {"success": True}

            elif step.action == PlaywrightAction.ASSERT:
                return await self._execute_assertion(step)

            else:
                return {"success": False, "error": f"Unknown action: {step.action}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_assertion(self, step: PlaywrightStep) -> Dict[str, Any]:
        try:
            if step.assertion_operator == AssertionOperator.EXISTS:
                element = await self.page.query_selector(step.selector)
                if element:
                    return {"success": True}
                return {"success": False, "error": f"Element not found: {step.selector}"}

            elif step.assertion_operator == AssertionOperator.NOT_EXISTS:
                element = await self.page.query_selector(step.selector)
                if not element:
                    return {"success": True}
                return {"success": False, "error": f"Element should not exist: {step.selector}"}

            elif step.assertion_operator == AssertionOperator.VISIBLE:
                await self.page.wait_for_selector(step.selector, state="visible", timeout=5000)
                return {"success": True}

            elif step.assertion_operator == AssertionOperator.NOT_VISIBLE:
                await self.page.wait_for_selector(step.selector, state="hidden", timeout=5000)
                return {"success": True}

            elif step.assertion_operator == AssertionOperator.EQUALS:
                element = await self.page.query_selector(step.selector)
                if not element:
                    return {"success": False, "error": f"Element not found: {step.selector}"}
                text = await element.text_content()
                if text == step.value:
                    return {"success": True}
                return {"success": False, "error": f"Expected '{step.value}', got '{text}'"}

            elif step.assertion_operator == AssertionOperator.CONTAINS:
                element = await self.page.query_selector(step.selector)
                if not element:
                    return {"success": False, "error": f"Element not found: {step.selector}"}
                text = await element.text_content()
                if step.value in text:
                    return {"success": True}
                return {"success": False, "error": f"Expected to contain '{step.value}', got '{text}'"}

            elif step.assertion_operator == AssertionOperator.NOT_CONTAINS:
                element = await self.page.query_selector(step.selector)
                if not element:
                    return {"success": False, "error": f"Element not found: {step.selector}"}
                text = await element.text_content()
                if step.value not in text:
                    return {"success": True}
                return {"success": False, "error": f"Should not contain '{step.value}', got '{text}'"}

            else:
                return {"success": False, "error": f"Unknown assertion operator: {step.assertion_operator}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_test_case(self, test_case: PlaywrightTestCase) -> PlaywrightTestResult:
        start_time = datetime.now()
        logs = []
        passed = True
        error_message = ""
        screenshot_path = ""

        try:
            await self._setup_browser()

            if test_case.viewport_width and test_case.viewport_height:
                await self.page.set_viewport_size(
                    {"width": test_case.viewport_width, "height": test_case.viewport_height}
                )

            for step in test_case.steps:
                result = await self._execute_step(step)
                logs.append(f"Step {step.action.value}: {step.selector} -> {'SUCCESS' if result['success'] else 'FAILED'}")

                if not result["success"]:
                    passed = False
                    error_message = result.get("error", "")
                    screenshot_path = await self._take_screenshot(test_case.id)
                    break

            if passed:
                screenshot_path = await self._take_screenshot(test_case.id)

        except Exception as e:
            passed = False
            error_message = str(e)
            if self.page:
                screenshot_path = await self._take_screenshot(test_case.id)

        finally:
            await self._teardown_browser()

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return PlaywrightTestResult(
            test_case_id=test_case.id,
            test_case_name=test_case.name,
            passed=passed,
            duration_ms=duration_ms,
            error_message=error_message,
            screenshot_path=screenshot_path,
            logs=logs,
        )

    async def _take_screenshot(self, test_id: str) -> str:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_dir = os.path.join("reports", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{test_id}_{timestamp}.png")
            await self.page.screenshot(path=path, full_page=True)
            return path
        except Exception:
            return ""

    async def run_test_suite(self, test_cases: List[PlaywrightTestCase]) -> PlaywrightTestReport:
        start_time = datetime.now()
        results = []
        passed_count = 0

        for test_case in test_cases:
            result = await self.run_test_case(test_case)
            results.append(result)
            if result.passed:
                passed_count += 1

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return PlaywrightTestReport(
            total_tests=len(test_cases),
            passed_tests=passed_count,
            failed_tests=len(test_cases) - passed_count,
            duration_ms=duration_ms,
            results=results,
            start_time=start_time,
            end_time=end_time,
        )

    def generate_report(self, report: PlaywrightTestReport, output_path: str = None) -> str:
        report_dict = {
            "summary": {
                "total_tests": report.total_tests,
                "passed_tests": report.passed_tests,
                "failed_tests": report.failed_tests,
                "pass_rate": f"{(report.passed_tests / report.total_tests * 100) if report.total_tests > 0 else 0:.2f}%",
                "duration_ms": report.duration_ms,
                "start_time": report.start_time.isoformat(),
                "end_time": report.end_time.isoformat(),
            },
            "details": [
                {
                    "test_name": r.test_case_name,
                    "test_id": r.test_case_id,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "error": r.error_message,
                    "screenshot": r.screenshot_path,
                    "logs": r.logs,
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

    def is_playwright_available(self) -> bool:
        return self._playwright_available

    def create_login_test(
        self,
        base_url: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        expected_element_selector: str,
        username: str,
        password: str,
    ) -> PlaywrightTestCase:
        return PlaywrightTestCase(
            id="ui_login_test",
            name="UI登录测试",
            description="测试登录页面功能",
            browser=self.browser_type,
            base_url=base_url,
            steps=[
                PlaywrightStep(action=PlaywrightAction.NAVIGATE, value="/login"),
                PlaywrightStep(action=PlaywrightAction.WAIT),
                PlaywrightStep(action=PlaywrightAction.FILL, selector=username_selector, value=username),
                PlaywrightStep(action=PlaywrightAction.FILL, selector=password_selector, value=password),
                PlaywrightStep(action=PlaywrightAction.CLICK, selector=submit_selector),
                PlaywrightStep(action=PlaywrightAction.WAIT),
                PlaywrightStep(action=PlaywrightAction.ASSERT, selector=expected_element_selector, assertion_operator=AssertionOperator.VISIBLE),
            ],
        )