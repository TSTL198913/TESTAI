import pytest
import os
import uuid
import time
import socket
import logging
from tests.ui.utils.config import config
from tests.ui.utils.logger import test_logger
from tests.ui.pages.login_page import LoginPage
from tests.ui.pages.workflow_page import WorkflowPage


logging.basicConfig(level=logging.INFO)


def _is_reachable(url: str, timeout: float = 1.0) -> bool:
    """检测目标 URL 是否可达（TCP 连通即可）。"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def require_live_frontend():
    """会话级守卫：前端服务不可达时跳过整个 UI 测试套件。

    UI 测试依赖运行中的前端 (localhost:3000) 和后端 (localhost:8000)。
    不可达时跳过，避免将"环境不具备"误报为"测试失败"。
    """
    if not _is_reachable(config.base_url):
        pytest.skip(
            f"UI 测试需要运行中的前端服务 ({config.base_url} 不可达)。"
            "请先启动前端服务。",
            allow_module_level=False,
        )
    if not _is_reachable(config.get_api_url()):
        pytest.skip(
            f"UI 测试需要运行中的后端 API ({config.get_api_url()} 不可达)。"
            "请先启动: uvicorn src.platform.api:app --port 8000",
            allow_module_level=False,
        )
    yield


@pytest.fixture(scope="session")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright not installed")
    
    chrome_executable = config.get_chrome_executable()
    if not chrome_executable:
        pytest.skip("Chrome browser not found")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.headless,
            executable_path=chrome_executable,
            slow_mo=config.slow_mo,
            args=config.get_browser_args(),
        )
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def page(browser):
    context = browser.new_context(viewport={"width": config.viewport_width, "height": config.viewport_height})
    page = context.new_page()
    page.set_default_timeout(config.page_timeout)
    yield page
    context.close()


@pytest.fixture(scope="function")
def logged_in_page(page):
    login_page = LoginPage(page)
    
    for attempt in range(config.retry_attempts):
        try:
            test_logger.log_step(f"Login attempt {attempt + 1}/{config.retry_attempts}", f"Logging in to {config.base_url}")
            
            success = login_page.login("admin", "password", config.base_url, max_retries=2)
            
            if success:
                test_logger.log_step("Login successful", f"Successfully logged in to {config.base_url}")
                yield page
                return
            
            if attempt < config.retry_attempts - 1:
                test_logger.warning(f"Login attempt {attempt + 1} failed, retrying in {config.retry_delay}s")
                time.sleep(config.retry_delay)
                page.reload()
        except Exception as e:
            test_logger.error(f"Login attempt {attempt + 1} exception: {e}")
            page.screenshot(path=f"login_error_attempt_{attempt + 1}.png")
            if attempt < config.retry_attempts - 1:
                time.sleep(config.retry_delay)
                page.reload()
    
    test_logger.critical("All login attempts failed")
    raise RuntimeError("Failed to login after multiple attempts")


@pytest.fixture(scope="function")
def test_workflow_factory(logged_in_page):
    created_workflow_ids = []
    workflow_page = WorkflowPage(logged_in_page)
    
    def create_workflow(name=None, description=None):
        workflow_name = name or f"测试工作流_{str(uuid.uuid4())[:8]}"
        
        try:
            workflow_page.load(config.base_url)
            workflow_page.create_workflow(name=workflow_name, description=description)
            created_workflow_ids.append(workflow_name)
            return workflow_name
        except Exception as e:
            test_logger.error(f"Failed to create workflow '{workflow_name}': {e}")
            raise
    
    yield create_workflow
    
    for wf_name in created_workflow_ids:
        try:
            workflow_page.load(config.base_url)
            workflow_page.delete_workflow(wf_name)
            test_logger.log_step("Cleanup", f"Deleted workflow '{wf_name}'")
        except Exception as e:
            test_logger.warning(f"Cleanup failed for workflow '{wf_name}': {e}")


@pytest.fixture(scope="function")
def api_client():
    api_base = config.get_api_url()
    
    class APIClient:
        def __init__(self):
            self.session = None
            self.token = None
        
        def login(self, username="admin", password="password"):
            import requests
            if self.session is None:
                self.session = requests.Session()
            
            for attempt in range(config.retry_attempts):
                try:
                    response = self.session.post(
                        f"{api_base}/auth/login",
                        json={"username": username, "password": password}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        self.token = data.get("access_token")
                        self.session.headers["Authorization"] = f"Bearer {self.token}"
                        return True
                except Exception as e:
                    test_logger.warning(f"API login attempt {attempt + 1} failed: {e}")
                    if attempt < config.retry_attempts - 1:
                        time.sleep(config.retry_delay)
            return False
        
        def delete_workflow(self, workflow_id):
            if self.session and self.token:
                for attempt in range(config.retry_attempts):
                    try:
                        response = self.session.delete(f"{api_base}/workflow/{workflow_id}")
                        if response.status_code == 200:
                            return True
                    except Exception as e:
                        test_logger.warning(f"Delete workflow attempt {attempt + 1} failed: {e}")
                        if attempt < config.retry_attempts - 1:
                            time.sleep(config.retry_delay)
            return False
    
    client = APIClient()
    client.login()
    yield client


@pytest.fixture(scope="function")
def assertions(page):
    from utils.assertions import Assertions
    return Assertions(page)


@pytest.fixture(scope="function")
def login_page(page):
    return LoginPage(page)


@pytest.fixture(scope="function")
def workflow_page(page):
    return WorkflowPage(page)


@pytest.fixture(scope="function")
def governance_page(page):
    from pages.governance_page import GovernancePage
    return GovernancePage(page)


@pytest.fixture(scope="function")
def dashboard_page(page):
    from pages.dashboard_page import DashboardPage
    return DashboardPage(page)