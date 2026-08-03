from .base_page import BasePage
try:
    from playwright.sync_api import Page, expect
    _playwright_available = True
except ImportError:
    _playwright_available = False
    Page = None
    expect = None
import uuid


class WorkflowPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.create_btn = '[data-testid="create-workflow-btn"]'
        self.create_modal = '[data-testid="create-workflow-modal"]'
        self.name_input = '[data-testid="workflow-name-input"]'
        self.desc_input = 'textarea[placeholder="请输入工作流描述"]'
        self.task_count_input = 'input[type="number"]'
        self.submit_btn = '[data-testid="workflow-submit-btn"]'
        self.workflow_cards = '[data-testid*="workflow-card-"]'
        self.workflow_name_pattern = '[data-testid*="workflow-name-"]'
        self.workflow_status_pattern = '[data-testid*="workflow-status-"]'
        self.workflow_action_pattern = '[data-testid*="workflow-execute-"], [data-testid*="workflow-retry-"], [data-testid*="workflow-pause-"]'
        self.workflow_delete_pattern = '[data-testid*="workflow-delete-"]'
        self.workflow_execute_pattern = '[data-testid*="workflow-execute-"]'
        self.error_message_pattern = '[data-testid="workflow-error-message"]'

    def load(self, base_url: str = "http://localhost:3000") -> None:
        self.go_to(f"{base_url}/workflow")
        self.wait_for_page_ready()

    def click_create_workflow(self) -> None:
        self.click(self.create_btn)
        self.wait_for_visible(self.create_modal, timeout=5000)

    def fill_workflow_name(self, name: str) -> None:
        self.fill(self.name_input, name)

    def fill_workflow_description(self, description: str) -> None:
        self.fill(self.desc_input, description)

    def fill_task_count(self, count: int) -> None:
        self.fill(self.task_count_input, str(count))

    def click_submit(self) -> None:
        self.click(self.submit_btn)

    def create_workflow(self, name: str = None, description: str = None, task_count: int = None) -> str:
        workflow_name = name or f"测试工作流_{str(uuid.uuid4())[:8]}"
        
        self.click_create_workflow()
        self.fill_workflow_name(workflow_name)
        
        if description:
            self.fill_workflow_description(description)
        
        if task_count is not None:
            self.fill_task_count(task_count)
        
        self.click_submit()
        self.wait(1.5)
        
        return workflow_name

    def is_workflow_created(self, workflow_name: str, timeout: int = 10000) -> bool:
        import time
        start_time = time.time()
        while time.time() - start_time < timeout / 1000:
            card = self.get_workflow_card(workflow_name)
            if card:
                return True
            time.sleep(0.5)
        return False

    def get_workflow_card(self, workflow_name: str):
        cards = self.get_all_locators(self.workflow_cards)
        for card in cards:
            name_element = card.locator(self.workflow_name_pattern)
            if name_element.count() > 0 and name_element.inner_text() == workflow_name:
                return card
        return None

    def get_workflow_status(self, workflow_name: str) -> str:
        card = self.get_workflow_card(workflow_name)
        if card:
            status_element = card.locator(self.workflow_status_pattern)
            if status_element.count() > 0:
                return status_element.inner_text()
        return ""

    def execute_workflow(self, workflow_name: str) -> bool:
        card = self.get_workflow_card(workflow_name)
        if not card:
            return False
        
        execute_button = card.locator(self.workflow_execute_pattern)
        if execute_button.count() == 0:
            execute_button = card.locator('button:has-text("执行")')
        
        if execute_button.count() > 0:
            execute_button.click()
            return True
        return False

    def delete_workflow(self, workflow_name: str) -> bool:
        card = self.get_workflow_card(workflow_name)
        if not card:
            return False
        
        self.handle_dialog(True)
        
        delete_button = card.locator(self.workflow_delete_pattern)
        if delete_button.count() > 0:
            delete_button.click()
            self.wait(1.0)
            return True
        
        return False

    def verify_workflow_deleted(self, workflow_name: str) -> bool:
        return not self.is_workflow_created(workflow_name, timeout=3000)

    def get_workflow_count(self) -> int:
        return self.page.locator(self.workflow_cards).count()

    def check_error_message(self) -> bool:
        error_messages = self.page.locator(self.error_message_pattern)
        return error_messages.count() > 0

    def get_progress_bar_width(self, workflow_name: str) -> str:
        card = self.get_workflow_card(workflow_name)
        if card:
            progress_bar = card.locator('.bg-blue-600.h-2.rounded-full')
            if progress_bar.count() > 0:
                return progress_bar.get_attribute("style")
        return ""

    def verify_create_modal_visible(self) -> None:
        expect(self.page.locator(self.create_modal)).to_be_visible()

    def verify_create_button_visible(self) -> None:
        expect(self.page.locator(self.create_btn)).to_be_visible()

    def verify_workflow_list_page(self) -> None:
        expect(self.page.locator('h3:has-text("工作流列表")')).to_be_visible()
        expect(self.page.locator('p:has-text("管理和执行自动化测试工作流")')).to_be_visible()
        expect(self.page.locator(self.create_btn)).to_be_visible()