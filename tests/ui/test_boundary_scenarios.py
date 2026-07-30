import pytest
import uuid
from playwright.sync_api import Page
from tests.ui.pages.login_page import LoginPage
from tests.ui.pages.workflow_page import WorkflowPage
from tests.ui.pages.governance_page import GovernancePage
from tests.ui.utils.assertions import Assertions
from tests.ui.utils.config import config


class TestBoundaryScenarios:
    """边界场景和异常测试 - 使用Page Object模式"""

    def test_create_workflow_with_extremely_long_name(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        very_long_name = "a" * 200
        
        workflow_page.click_create_workflow()
        workflow_page.fill_workflow_name(very_long_name)
        workflow_page.click_submit()
        
        assertions.assert_element_visible(workflow_page.create_modal)

    def test_create_workflow_with_special_characters(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        special_name = f"工作流@#$%^&*()_+-=[]{{}}|;':\",./<>?{str(uuid.uuid4())[:4]}"
        
        workflow_page.click_create_workflow()
        workflow_page.fill_workflow_name(special_name)
        workflow_page.click_submit()
        
        assertions.assert_true(workflow_page.is_workflow_created(special_name))

    def test_workflow_duplicate_name(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        duplicate_name = f"重复名称工作流_{str(uuid.uuid4())[:4]}"
        
        workflow_page.create_workflow(name=duplicate_name)
        
        workflow_page.create_workflow(name=duplicate_name)
        
        cards = workflow_page.get_all_locators(workflow_page.workflow_cards)
        found_count = 0
        for card in cards:
            name_element = card.locator(workflow_page.workflow_name_pattern)
            if name_element.count() > 0 and name_element.inner_text() == duplicate_name:
                found_count += 1
        assertions.assert_true(found_count >= 1)

    def test_empty_workflow_description(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_name = f"无描述工作流_{str(uuid.uuid4())[:8]}"
        
        workflow_page.create_workflow(name=workflow_name)
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))

    def test_workflow_task_count_boundary(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_name = f"边界测试工作流_{str(uuid.uuid4())[:8]}"
        
        workflow_page.click_create_workflow()
        workflow_page.fill_workflow_name(workflow_name)
        workflow_page.fill_task_count(100)
        workflow_page.click_submit()
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))

    def test_workflow_task_count_zero(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_name = f"零任务工作流_{str(uuid.uuid4())[:8]}"
        
        workflow_page.click_create_workflow()
        workflow_page.fill_workflow_name(workflow_name)
        workflow_page.fill_task_count(0)
        workflow_page.click_submit()
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))

    def test_governance_filter_empty_state(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('approved')
        governance_page.verify_table_visible()

    def test_workflow_page_no_cards(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        
        workflow_page.load(config.base_url)
        workflow_page.verify_create_button_visible()

    def test_login_with_special_characters(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("admin' OR '1'='1")
        login_page.enter_password("password")
        login_page.click_login()
        
        assertions.assert_url_contains("/login")

    def test_login_with_sql_injection(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("'; DROP TABLE users; --")
        login_page.enter_password("password")
        login_page.click_login()
        
        assertions.assert_url_contains("/login")