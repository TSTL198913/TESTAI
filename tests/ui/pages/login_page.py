from .base_page import BasePage
try:
    from playwright.sync_api import Page, expect
    _playwright_available = True
except ImportError:
    _playwright_available = False
    Page = None
    expect = None
import logging


class LoginPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.username_input = 'input[id="username"]'
        self.password_input = 'input[id="password"]'
        self.submit_button = 'button[type="submit"]'
        self.login_error = '[data-testid="login-error"]'
        self.eye_icon = 'button:has(svg[class*="Eye"])'

    def load(self, base_url: str = "http://localhost:3000") -> None:
        self.go_to(f"{base_url}/login")
        self.wait_for_page_ready()

    def enter_username(self, username: str) -> None:
        self.fill(self.username_input, username)

    def enter_password(self, password: str) -> None:
        self.fill(self.password_input, password)

    def click_login(self) -> None:
        self.click(self.submit_button)

    def login(self, username: str, password: str, base_url: str = "http://localhost:3000", max_retries: int = 2) -> bool:
        for attempt in range(max_retries):
            try:
                self.load(base_url)
                self.enter_username(username)
                self.enter_password(password)
                self.click_login()
                
                try:
                    self.wait_for_url(f"{base_url}/", timeout=30000)
                    return True
                except Exception:
                    current_url = self.get_current_url()
                    if current_url != f"{base_url}/login":
                        return True
                    
                    if self.is_visible(self.login_error, timeout=3000):
                        if attempt < max_retries - 1:
                            self.logger.info(f"Login failed, retrying (attempt {attempt + 1}/{max_retries})")
                            continue
                        else:
                            self.screenshot(f"login_failure_attempt_{attempt + 1}.png")
                            return False
            except Exception as e:
                self.logger.error(f"Login attempt {attempt + 1} failed: {e}")
                self.screenshot(f"login_exception_attempt_{attempt + 1}.png")
                if attempt < max_retries - 1:
                    continue
                return False
        
        return False

    def check_login_error(self) -> bool:
        return self.is_visible(self.login_error)

    def toggle_password_visibility(self) -> None:
        eye_button = self.page.locator(self.eye_icon)
        if eye_button.count() > 0:
            eye_button.click()

    def get_password_input_type(self) -> str:
        return self.get_attribute(self.password_input, "type")

    def verify_login_page_displayed(self) -> None:
        expect(self.page.locator(self.username_input)).to_be_visible()
        expect(self.page.locator(self.password_input)).to_be_visible()
        expect(self.page.locator(self.submit_button)).to_be_visible()