from .base_page import BasePage
try:
    from playwright.sync_api import Page, expect
    _playwright_available = True
except ImportError:
    _playwright_available = False
    Page = None
    expect = None


class DashboardPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.dashboard_title = '[data-testid="dashboard-title"]'
        self.nav_items = {
            '仪表盘': 'nav a:has-text("仪表盘")',
            '工作流': 'nav a:has-text("工作流")',
            '治理流程': 'nav a:has-text("治理流程")',
        }

    def load(self, base_url: str = "http://localhost:3000") -> None:
        self.go_to(f"{base_url}/")
        self.wait_for_page_ready()

    def is_dashboard_visible(self) -> bool:
        return self.is_visible(self.dashboard_title)

    def navigate_to(self, menu_item: str) -> None:
        if menu_item in self.nav_items:
            self.click(self.nav_items[menu_item])
            self.wait_for_navigation()
        else:
            raise ValueError(f"Unknown menu item: {menu_item}")

    def verify_navigation(self, expected_page_title: str = None) -> bool:
        if expected_page_title:
            return expected_page_title in self.get_current_url()
        return self.is_visible('h2')

    def verify_page_title(self, title_text: str) -> None:
        expect(self.page.locator('h2')).to_have_text(title_text)