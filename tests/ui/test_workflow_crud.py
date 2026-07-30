import pytest
import uuid
from playwright.sync_api import Page
from tests.ui.pages.workflow_page import WorkflowPage
from tests.ui.utils.assertions import Assertions
from tests.ui.utils.config import config


class TestWorkflowCRUD:
    """工作流CRUD UI测试 - 使用Page Object模式"""

    def test_workflow_list_page(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        workflow_page.load(config.base_url)
        workflow_page.verify_workflow_list_page()

    def test_create_workflow_with_valid_data(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        workflow_name = f"深度测试工作流_{str(uuid.uuid4())[:8]}"
        workflow_page.create_workflow(
            name=workflow_name,
            description="这是一个深度测试工作流",
            task_count=5
        )
        
        assertions.assert_true(workflow_page.is_workflow_created(workflow_name))

    def test_create_workflow_empty_name_validation(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        initial_count = workflow_page.get_workflow_count()
        
        workflow_page.click_create_workflow()
        workflow_page.click_submit()
        
        assertions.assert_element_visible(workflow_page.create_modal)
        assertions.assert_true(workflow_page.check_error_message())
        
        final_count = workflow_page.get_workflow_count()
        assertions.assert_equal(final_count, initial_count)

    def test_workflow_status_display(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        cards = workflow_page.get_all_locators(workflow_page.workflow_cards)
        if cards:
            card = cards[0]
            status_badge = card.locator(workflow_page.workflow_status_pattern)
            if status_badge.count() > 0:
                from playwright.sync_api import expect
                expect(status_badge).to_be_visible()
                badge_text = status_badge.inner_text()
                assertions.assert_in(badge_text, ["已完成", "待执行", "运行中", "失败", "已暂停", "已定义"])

    def test_workflow_progress_bar(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        cards = workflow_page.get_all_locators(workflow_page.workflow_cards)
        if cards:
            first_card = cards[0]
            progress_bar = first_card.locator('.bg-blue-600.h-2.rounded-full')
            assertions.assert_element_count(progress_bar, 1)
            width_style = progress_bar.get_attribute("style")
            assertions.assert_true(width_style is not None)
            assertions.assert_in("width", width_style)

    def test_workflow_actions_buttons(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        cards = workflow_page.get_all_locators(workflow_page.workflow_cards)
        if cards:
            first_card = cards[0]
            action_buttons = first_card.locator(workflow_page.workflow_action_pattern)
            from playwright.sync_api import expect
            expect(action_buttons.first).to_be_visible()
            assertions.assert_element_count_at_least(workflow_page.workflow_action_pattern, 2)

    def test_workflow_execute_action(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        cards = workflow_page.get_all_locators(workflow_page.workflow_cards)
        target_card = None
        
        for card in cards:
            status_element = card.locator(workflow_page.workflow_status_pattern)
            if status_element.count() > 0 and status_element.inner_text() == "待执行":
                target_card = card
                break
        
        if target_card:
            name_element = target_card.locator(workflow_page.workflow_name_pattern)
            card_name = name_element.inner_text() if name_element.count() > 0 else "Unknown"
            initial_status = target_card.locator(workflow_page.workflow_status_pattern).inner_text()
            
            execute_button = target_card.locator(workflow_page.workflow_execute_pattern)
            if execute_button.count() == 0:
                execute_button = target_card.locator('button:has-text("执行")')
            
            if execute_button.count() > 0:
                execute_button.click()
                workflow_page.wait_for_navigation()
                workflow_page.load(config.base_url)
                
                updated_status = workflow_page.get_workflow_status(card_name)
                assertions.assert_not_equal(updated_status, initial_status)
                assertions.assert_in(updated_status, ["运行中", "已完成"])

    def test_workflow_delete_action(self, logged_in_page: Page):
        workflow_page = WorkflowPage(logged_in_page)
        assertions = Assertions(logged_in_page)
        
        workflow_page.load(config.base_url)
        
        delete_workflow_name = f"待删除工作流_{str(uuid.uuid4())[:8]}"
        workflow_page.create_workflow(name=delete_workflow_name)
        
        assertions.assert_true(workflow_page.is_workflow_created(delete_workflow_name))
        
        workflow_page.delete_workflow(delete_workflow_name)
        
        assertions.assert_true(workflow_page.verify_workflow_deleted(delete_workflow_name))