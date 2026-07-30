import pytest
import random
import uuid
from playwright.sync_api import Page
from tests.ui.pages.login_page import LoginPage
from tests.ui.pages.dashboard_page import DashboardPage
from tests.ui.pages.workflow_page import WorkflowPage
from tests.ui.pages.governance_page import GovernancePage
from tests.ui.utils.assertions import Assertions
from tests.ui.utils.config import config


class TestRealUserScenarios:
    """真实用户测试场景 - 使用Page Object模式"""

    def test_real_user_login_and_navigation(self, page: Page):
        login_page = LoginPage(page)
        dashboard_page = DashboardPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("admin")
        login_page.enter_password("password")
        login_page.click_login()
        
        assertions.assert_url_not_contains("/login")
        
        for item in ['仪表盘', '工作流', '治理流程']:
            dashboard_page.navigate_to(item)
            assertions.assert_element_visible('h2')

    def test_real_user_workflow_creation_scenario(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_page.click_create_workflow()
        workflow_page.fill_workflow_name("")
        workflow_page.click_submit()
        
        assertions.assert_element_visible(workflow_page.create_modal)
        
        workflow_name = f"用户测试工作流_{str(uuid.uuid4())[:6]}"
        workflow_page.fill_workflow_name(workflow_name)
        workflow_page.fill_workflow_description("这是一个由真实用户创建的测试工作流")
        workflow_page.fill_task_count(random.randint(1, 10))
        
        workflow_page.click_submit()
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))

    def test_real_user_governance_approval_scenario(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('pending')
        
        rows = governance_page.get_approval_rows()
        if rows:
            governance_page.view_approval_detail(0)
            
            assertions.assert_element_visible(governance_page.detail_title)
            
            governance_page.close_detail()
            
            governance_page.approve_approval(0)
            
            governance_page.click_filter('approved')

    def test_real_user_error_handling_scenario(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        
        login_page.enter_username("")
        login_page.enter_password("")
        login_page.click_login()
        
        assertions.assert_element_visible(login_page.login_error)
        
        login_page.enter_username("wronguser123")
        login_page.enter_password("wrongpass456")
        login_page.click_login()
        
        assertions.assert_element_visible(login_page.login_error)
        
        login_page.enter_username("admin")
        login_page.enter_password("password")
        login_page.click_login()
        
        assertions.assert_url_not_contains("/login")

    def test_real_user_workflow_execution_scenario(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_name = f"执行测试工作流_{str(uuid.uuid4())[:8]}"
        workflow_page.create_workflow(name=workflow_name)
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))
        
        initial_status = workflow_page.get_workflow_status(workflow_name)
        
        if workflow_page.execute_workflow(workflow_name):
            workflow_page.wait(3.0)
            workflow_page.load(config.base_url)
            
            updated_status = workflow_page.get_workflow_status(workflow_name)
            
            assertions.assert_not_equal(updated_status, initial_status)
            assertions.assert_in(updated_status, ["运行中", "已完成"])

    def test_real_user_quick_actions_scenario(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        
        for filter_key in ['all', 'pending', 'approved', 'rejected']:
            governance_page.click_filter(filter_key)
            governance_page.verify_table_visible()
        
        governance_page.execute_governance()
        
        governance_page.click_filter('pending')