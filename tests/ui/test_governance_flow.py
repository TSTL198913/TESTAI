import pytest
from playwright.sync_api import Page
from tests.ui.pages.governance_page import GovernancePage
from tests.ui.utils.assertions import Assertions
from tests.ui.utils.config import config


class TestGovernanceFlow:
    """治理流程UI测试 - 使用Page Object模式"""

    def test_governance_page_load(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        governance_page.load(config.base_url)
        governance_page.verify_page_loaded()

    def test_governance_status_filter_all(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('all')
        governance_page.verify_table_visible()

    def test_governance_status_filter_pending(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('pending')
        governance_page.verify_table_visible()

    def test_governance_status_filter_approved(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('approved')
        governance_page.verify_table_visible()

    def test_governance_status_filter_rejected(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.click_filter('rejected')
        governance_page.verify_table_visible()

    def test_governance_table_columns(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.verify_table_columns()

    def test_governance_view_detail(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        governance_page.load(config.base_url)
        
        rows = governance_page.get_approval_rows()
        if rows:
            governance_page.view_approval_detail(0)
            
            assertions.assert_element_visible(governance_page.detail_title)
            
            governance_page.close_detail()

    def test_governance_execute_action(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.execute_governance()
        governance_page.verify_table_visible()

    def test_governance_empty_state(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        assertions = Assertions(logged_in_page)

        governance_page.load(config.base_url)
        governance_page.click_filter('pending')

        rows = governance_page.get_approval_rows()
        if not rows:
            assertions.assert_element_visible('p:has-text("暂无审批任务")')
        else:
            # 有审批行时, 断言表格至少渲染 1 行。
            # 禁止用 assert_element_visible('tbody tr') —— pending 有 9 行时该选择器匹配多元素,
            # 触发 Playwright strict mode violation (E2E 真实执行暴露)。
            # 业务意图是"行存在即表格已渲染", 用 count_at_least 精确表达且无歧义。
            assertions.assert_element_count_at_least('tbody tr', 1)

    def test_governance_component_display(self, logged_in_page: Page):
        governance_page = GovernancePage(logged_in_page)
        
        governance_page.load(config.base_url)
        governance_page.verify_table_visible()