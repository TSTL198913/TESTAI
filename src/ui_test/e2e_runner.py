import os
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .playwright_runner import PlaywrightRunner, PlaywrightTestCase, PlaywrightStep, PlaywrightAction, AssertionOperator, BrowserType


class E2EStepType(str, Enum):
    NAVIGATE = "navigate"
    AUTH = "auth"
    ACTION = "action"
    ASSERT = "assert"
    WAIT = "wait"
    CLEANUP = "cleanup"


@dataclass
class E2EStep:
    step_type: E2EStepType
    name: str
    selector: str = ""
    value: str = ""
    action: str = ""
    assertion: str = ""
    assertion_value: str = ""
    wait_time_ms: int = 0
    skip_if_failed: bool = False


@dataclass
class E2EFlow:
    flow_id: str
    name: str
    description: str = ""
    base_url: str = ""
    browser: BrowserType = BrowserType.CHROMIUM
    steps: List[E2EStep] = field(default_factory=list)
    auth_required: bool = False
    username: str = ""
    password: str = ""


@dataclass
class E2EResult:
    flow_id: str
    flow_name: str
    passed: bool
    step_results: List[Dict] = field(default_factory=list)
    duration_ms: int = 0
    error_message: str = ""


class E2ERunner:
    def __init__(self, browser_type: BrowserType = BrowserType.CHROMIUM, headless: bool = True):
        self.browser_type = browser_type
        self.headless = headless
        self.runner = PlaywrightRunner(browser_type=browser_type, headless=headless)

    async def run_flow(self, flow: E2EFlow) -> E2EResult:
        start_time = datetime.now()
        step_results = []
        passed = True
        error_message = ""

        try:
            await self.runner._setup_browser()

            if flow.viewport_width and flow.viewport_height:
                await self.runner.page.set_viewport_size(
                    {"width": flow.viewport_width, "height": flow.viewport_height}
                )

            for step in flow.steps:
                step_start = datetime.now()
                result = await self._execute_e2e_step(step, flow.base_url)
                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                step_results.append({
                    "step_name": step.name,
                    "step_type": step.step_type.value,
                    "success": result["success"],
                    "duration_ms": step_duration,
                    "error": result.get("error", ""),
                })

                if not result["success"]:
                    passed = False
                    error_message = result.get("error", "")
                    
                    if step.skip_if_failed:
                        break

        except Exception as e:
            passed = False
            error_message = str(e)
            step_results.append({
                "step_name": "Exception",
                "step_type": "exception",
                "success": False,
                "error": str(e),
            })

        finally:
            await self.runner._teardown_browser()

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return E2EResult(
            flow_id=flow.flow_id,
            flow_name=flow.name,
            passed=passed,
            step_results=step_results,
            duration_ms=duration_ms,
            error_message=error_message,
        )

    async def _execute_e2e_step(self, step: E2EStep, base_url: str = "") -> Dict:
        try:
            if step.step_type == E2EStepType.NAVIGATE:
                url = step.value
                if not url.startswith("http") and base_url:
                    url = base_url + url
                await self.runner.page.goto(url, wait_until="domcontentloaded")
                return {"success": True}

            elif step.step_type == E2EStepType.AUTH:
                await self.runner.page.goto(f"{base_url}/login", wait_until="domcontentloaded")
                await self.runner.page.fill('input[name="username"]', step.username)
                await self.runner.page.fill('input[name="password"]', step.password)
                await self.runner.page.click('button[type="submit"]')
                await self.runner.page.wait_for_load_state("networkidle")
                return {"success": True}

            elif step.step_type == E2EStepType.ACTION:
                action_map = {
                    "click": PlaywrightAction.CLICK,
                    "fill": PlaywrightAction.FILL,
                    "type": PlaywrightAction.TYPE,
                    "clear": PlaywrightAction.CLEAR,
                    "select": PlaywrightAction.SELECT,
                    "check": PlaywrightAction.CHECK,
                    "uncheck": PlaywrightAction.UNCHECK,
                    "hover": PlaywrightAction.HOVER,
                    "scroll": PlaywrightAction.SCROLL,
                }

                playwright_action = action_map.get(step.action, PlaywrightAction.CLICK)
                step_result = await self.runner._execute_step(
                    PlaywrightStep(
                        action=playwright_action,
                        selector=step.selector,
                        value=step.value,
                    )
                )
                return step_result

            elif step.step_type == E2EStepType.ASSERT:
                assertion_map = {
                    "equals": AssertionOperator.EQUALS,
                    "contains": AssertionOperator.CONTAINS,
                    "not_contains": AssertionOperator.NOT_CONTAINS,
                    "exists": AssertionOperator.EXISTS,
                    "not_exists": AssertionOperator.NOT_EXISTS,
                    "visible": AssertionOperator.VISIBLE,
                    "not_visible": AssertionOperator.NOT_VISIBLE,
                }

                operator = assertion_map.get(step.assertion, AssertionOperator.EXISTS)
                step_result = await self.runner._execute_step(
                    PlaywrightStep(
                        action=PlaywrightAction.ASSERT,
                        selector=step.selector,
                        value=step.assertion_value,
                        assertion_operator=operator,
                    )
                )
                return step_result

            elif step.step_type == E2EStepType.WAIT:
                if step.wait_time_ms > 0:
                    await self.runner.page.wait_for_timeout(step.wait_time_ms)
                else:
                    await self.runner.page.wait_for_load_state("networkidle")
                return {"success": True}

            elif step.step_type == E2EStepType.CLEANUP:
                await self.runner.page.goto(f"{base_url}/logout")
                return {"success": True}

            else:
                return {"success": False, "error": f"Unknown step type: {step.step_type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_flows(self, flows: List[E2EFlow]) -> List[E2EResult]:
        results = []
        for flow in flows:
            result = await self.run_flow(flow)
            results.append(result)
        return results

    def create_login_flow(
        self,
        base_url: str,
        username: str,
        password: str,
        username_selector: str = 'input[name="username"]',
        password_selector: str = 'input[name="password"]',  # nosec B107
        submit_selector: str = 'button[type="submit"]',
        expected_selector: str = ".dashboard",
    ) -> E2EFlow:
        return E2EFlow(
            flow_id="e2e_login",
            name="用户登录流程",
            description="测试用户登录完整流程",
            base_url=base_url,
            steps=[
                E2EStep(
                    step_type=E2EStepType.NAVIGATE,
                    name="打开登录页面",
                    value="/login",
                ),
                E2EStep(
                    step_type=E2EStepType.WAIT,
                    name="等待页面加载",
                ),
                E2EStep(
                    step_type=E2EStepType.ACTION,
                    name="输入用户名",
                    selector=username_selector,
                    action="fill",
                    value=username,
                ),
                E2EStep(
                    step_type=E2EStepType.ACTION,
                    name="输入密码",
                    selector=password_selector,
                    action="fill",
                    value=password,
                ),
                E2EStep(
                    step_type=E2EStepType.ACTION,
                    name="点击登录按钮",
                    selector=submit_selector,
                    action="click",
                ),
                E2EStep(
                    step_type=E2EStepType.WAIT,
                    name="等待跳转",
                ),
                E2EStep(
                    step_type=E2EStepType.ASSERT,
                    name="验证跳转成功",
                    selector=expected_selector,
                    assertion="visible",
                ),
            ],
        )

    def create_crud_flow(
        self,
        base_url: str,
        username: str,
        password: str,
        entity_name: str,
        create_data: Dict,
        list_page: str = "/entities",
        create_page: str = "/entities/create",
    ) -> E2EFlow:
        steps = [
            E2EStep(
                step_type=E2EStepType.AUTH,
                name="登录系统",
                username=username,
                password=password,
            ),
            E2EStep(
                step_type=E2EStepType.NAVIGATE,
                name="进入列表页面",
                value=list_page,
            ),
            E2EStep(
                step_type=E2EStepType.WAIT,
                name="等待列表加载",
            ),
            E2EStep(
                step_type=E2EStepType.ACTION,
                name="点击创建按钮",
                selector='button:has-text("创建")',
                action="click",
            ),
            E2EStep(
                step_type=E2EStepType.WAIT,
                name="等待创建页面加载",
            ),
        ]

        for field_name, field_value in create_data.items():
            steps.append(E2EStep(
                step_type=E2EStepType.ACTION,
                name=f"填写{field_name}",
                selector=f'input[name="{field_name}"]',
                action="fill",
                value=str(field_value),
            ))

        steps.extend([
            E2EStep(
                step_type=E2EStepType.ACTION,
                name="提交表单",
                selector='button[type="submit"]',
                action="click",
            ),
            E2EStep(
                step_type=E2EStepType.WAIT,
                name="等待提交完成",
            ),
            E2EStep(
                step_type=E2EStepType.ASSERT,
                name="验证创建成功提示",
                selector=".toast-success",
                assertion="visible",
            ),
            E2EStep(
                step_type=E2EStepType.CLEANUP,
                name="登出系统",
            ),
        ])

        return E2EFlow(
            flow_id=f"e2e_{entity_name}_crud",
            name=f"{entity_name}增删改查流程",
            description=f"测试{entity_name}的完整CRUD流程",
            base_url=base_url,
            steps=steps,
        )