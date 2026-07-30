import pytest
from unittest.mock import Mock, patch
from tests.ui.pages.workflow_page import WorkflowPage
from tests.ui.pages.base_page import BasePage


class TestUiPageMethodSafety:
    def test_base_page_find_element_by_text_returns_none(self):
        mock_page = Mock()
        mock_container = Mock()
        mock_elements = Mock()
        mock_page.locator.return_value = mock_container
        mock_container.locator.return_value = mock_elements
        mock_elements.count.return_value = 5
        mock_elements.nth.return_value.inner_text.side_effect = Exception("Test exception")
        
        base_page = BasePage(mock_page)
        
        result = base_page.find_element_by_text("nonexistent text")
        
        assert result is None

    def test_base_page_click_button_by_text_raises(self):
        mock_page = Mock()
        mock_container = Mock()
        mock_buttons = Mock()
        mock_page.locator.return_value = mock_container
        mock_container.locator.return_value = mock_buttons
        mock_buttons.count.return_value = 0
        
        base_page = BasePage(mock_page)
        
        with pytest.raises(ValueError, match="Button with text"):
            base_page.click_button_by_text("nonexistent button")

    def test_workflow_page_is_workflow_created_empty_except(self):
        mock_page = Mock()
        mock_page.locator.return_value = Mock()
        mock_page.locator.return_value.wait_for.side_effect = Exception("Test timeout")
        
        base_page = BasePage(mock_page)
        workflow_page = WorkflowPage.__new__(WorkflowPage)
        workflow_page.page = mock_page
        workflow_page.create_btn = '[data-testid="create-workflow-btn"]'
        workflow_page.create_modal = '[data-testid="create-workflow-modal"]'
        workflow_page.name_input = '[data-testid="workflow-name-input"]'
        workflow_page.desc_input = 'textarea[placeholder="请输入工作流描述"]'
        workflow_page.task_count_input = 'input[type="number"]'
        workflow_page.submit_btn = '[data-testid="workflow-submit-btn"]'
        workflow_page.workflow_cards = '[data-testid*="workflow-card-"]'
        workflow_page.workflow_name_pattern = '[data-testid*="workflow-name-"]'
        workflow_page.workflow_status_pattern = '[data-testid*="workflow-status-"]'
        workflow_page.workflow_action_pattern = '[data-testid*="workflow-action-"]'
        workflow_page.workflow_delete_pattern = '[data-testid*="workflow-delete-"]'
        workflow_page.workflow_execute_pattern = '[data-testid*="workflow-action-execute-"]'
        workflow_page.workflow_progress_pattern = '[data-testid*="workflow-progress-"]'
        workflow_page.error_message_pattern = 'p:has-text("请输入工作流名称"), span:has-text("请输入工作流名称")'
        
        result = workflow_page.is_workflow_created("test_workflow")
        
        assert result is False

    def test_workflow_page_get_workflow_card_handles_empty_list(self):
        mock_page = Mock()
        mock_page.locator.return_value = Mock()
        mock_page.locator.return_value.count.return_value = 0
        
        base_page = BasePage(mock_page)
        workflow_page = WorkflowPage.__new__(WorkflowPage)
        workflow_page.page = mock_page
        workflow_page.workflow_cards = '[data-testid*="workflow-card-"]'
        workflow_page.workflow_name_pattern = '[data-testid*="workflow-name-"]'
        
        result = workflow_page.get_workflow_card("test_workflow")
        
        assert result is None

    def test_base_page_is_visible_handles_exception(self):
        mock_page = Mock()
        mock_page.locator.return_value = Mock()
        mock_page.locator.return_value.wait_for.side_effect = Exception("Test exception")
        
        base_page = BasePage(mock_page)
        
        result = base_page.is_visible("test_selector")
        
        assert result is False

    def test_base_page_is_hidden_handles_exception(self):
        mock_page = Mock()
        mock_page.locator.return_value = Mock()
        mock_page.locator.return_value.wait_for.side_effect = Exception("Test exception")
        
        base_page = BasePage(mock_page)
        
        result = base_page.is_hidden("test_selector")
        
        assert result is False