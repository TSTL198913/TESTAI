from .base_page import BasePage
from playwright.sync_api import Page, expect


class GovernancePage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.filter_all = '[data-testid="filter-all"], button:has-text("全部")'
        self.filter_pending = '[data-testid="filter-pending"], button:has-text("待审批")'
        self.filter_approved = '[data-testid="filter-approved"], button:has-text("已批准")'
        self.filter_rejected = '[data-testid="filter-rejected"], button:has-text("已拒绝")'
        self.execute_governance_btn = '[data-testid="execute-governance-btn"], button:has-text("执行治理")'
        self.approval_rows = '[data-testid*="approval-row-"]'
        self.approval_view_pattern = '[data-testid*="approval-view-"]'
        self.approval_approve_pattern = '[data-testid*="approval-approve-"]'
        self.table = 'table'
        self.detail_title = 'h3:has-text("审批详情")'
        self.close_button = 'button:has(svg[class*="X"]), button:has-text("关闭")'

    def load(self, base_url: str = "http://localhost:3000") -> None:
        self.go_to(f"{base_url}/governance")
        self.wait_for_page_ready()

    def click_filter(self, filter_type: str) -> None:
        filter_map = {
            'all': self.filter_all,
            'pending': self.filter_pending,
            'approved': self.filter_approved,
            'rejected': self.filter_rejected,
        }
        
        if filter_type in filter_map:
            selector = filter_map[filter_type]
            locator = self.page.locator(selector)
            if locator.count() > 0:
                locator.first.click()
                self.wait_for_navigation()
            else:
                raise ValueError(f"Filter button for '{filter_type}' not found")
        else:
            raise ValueError(f"Unknown filter type: {filter_type}")

    def execute_governance(self) -> None:
        locator = self.page.locator(self.execute_governance_btn)
        if locator.count() > 0:
            locator.first.click()
            self.wait(1.5)
        else:
            raise ValueError("Execute governance button not found")

    def get_approval_rows(self):
        return self.get_all_locators(self.approval_rows)

    def get_pending_rows(self):
        rows = self.get_approval_rows()
        pending = []
        for row in rows:
            status_element = row.locator('span:has-text("待审批")')
            if status_element.count() > 0:
                pending.append(row)
        return pending

    def view_approval_detail(self, row_index: int = 0) -> bool:
        rows = self.get_approval_rows()
        if rows:
            row = rows[row_index]
            eye_button = row.locator(self.approval_view_pattern)
            if eye_button.count() == 0:
                eye_button = row.locator('button:has(svg[class*="Eye"])')
            
            if eye_button.count() > 0:
                eye_button.click()
                return True
        return False

    def close_detail(self) -> None:
        locator = self.page.locator(self.close_button)
        if locator.count() > 0:
            locator.first.click()

    def approve_approval(self, row_index: int = 0) -> bool:
        rows = self.get_approval_rows()
        if rows:
            row = rows[row_index]
            approve_button = row.locator(self.approval_approve_pattern)
            if approve_button.count() == 0:
                approve_button = row.locator('button:has-text("批准")')
            
            if approve_button.count() > 0:
                approve_button.click()
                return True
        return False

    def verify_table_visible(self) -> None:
        expect(self.page.locator(self.table)).to_be_visible()

    def verify_page_loaded(self) -> None:
        expect(self.page.locator('button:has-text("全部")')).to_be_visible()
        expect(self.page.locator('button:has-text("待审批")')).to_be_visible()
        expect(self.page.locator('button:has-text("已批准")')).to_be_visible()
        expect(self.page.locator('button:has-text("已拒绝")')).to_be_visible()
        expect(self.page.locator('button:has-text("执行治理")')).to_be_visible()

    def verify_table_columns(self) -> None:
        headers = self.page.locator('thead th')
        expect(headers).to_have_count(5)
        expect(self.page.locator('th:has-text("事务ID")')).to_be_visible()
        expect(self.page.locator('th:has-text("组件")')).to_be_visible()
        expect(self.page.locator('th:has-text("状态")')).to_be_visible()
        expect(self.page.locator('th:has-text("创建时间")')).to_be_visible()
        expect(self.page.locator('th:has-text("操作")')).to_be_visible()

    def check_empty_state(self) -> bool:
        rows = self.page.locator('tbody tr')
        if rows.count() == 0:
            empty_text = self.page.locator('p:has-text("暂无审批任务")')
            return empty_text.count() > 0
        return False