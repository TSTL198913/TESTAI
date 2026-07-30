import pytest
from playwright.sync_api import Page
from tests.ui.pages.login_page import LoginPage
from tests.ui.pages.dashboard_page import DashboardPage
from tests.ui.utils.assertions import Assertions
from tests.ui.utils.config import config


class TestLoginFlow:
    """登录流程UI测试 - 使用Page Object模式"""

    def test_login_success(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("admin")
        login_page.enter_password("password")
        login_page.click_login()
        
        import time
        time.sleep(2)
        assertions.assert_url_not_contains("/login", timeout=30000)

    def test_login_invalid_credentials(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("wronguser")
        login_page.enter_password("wrongpass")
        login_page.click_login()
        
        assertions.assert_element_visible(login_page.login_error)

    def test_login_empty_fields(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.click_login()
        
        assertions.assert_element_visible(login_page.login_error)

    def test_password_show_hide(self, page: Page):
        login_page = LoginPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_password("testpassword")
        
        eye_icon = page.locator(login_page.eye_icon)
        if eye_icon.count() > 0:
            login_page.toggle_password_visibility()
            assertions.assert_element_attribute(login_page.password_input, "type", "text")
            
            login_page.toggle_password_visibility()
            assertions.assert_element_attribute(login_page.password_input, "type", "password")

    def test_navigation_to_dashboard_after_login(self, page: Page):
        login_page = LoginPage(page)
        dashboard_page = DashboardPage(page)
        assertions = Assertions(page)
        
        login_page.load(config.base_url)
        login_page.enter_username("admin")
        login_page.enter_password("password")
        login_page.click_login()
        
        assertions.assert_element_visible(dashboard_page.dashboard_title)