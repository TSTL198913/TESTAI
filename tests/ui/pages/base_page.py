try:
    from playwright.sync_api import Page, Locator
    _playwright_available = True
except ImportError:
    _playwright_available = False
    Page = None
    Locator = None

import time
import logging
from typing import Optional, List, Tuple


class BasePage:
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger(self.__class__.__name__)

    def wait_for(self, selector: str, timeout: int = 5000) -> Locator:
        locator = self.page.locator(selector)
        locator.wait_for(timeout=timeout)
        return locator

    def wait_for_visible(self, selector: str, timeout: int = 5000) -> Locator:
        locator = self.page.locator(selector)
        locator.wait_for(state="visible", timeout=timeout)
        return locator

    def wait_for_hidden(self, selector: str, timeout: int = 5000) -> Locator:
        locator = self.page.locator(selector)
        locator.wait_for(state="hidden", timeout=timeout)
        return locator

    def click(self, selector: str, timeout: int = 5000, force: bool = False) -> None:
        locator = self.wait_for_visible(selector, timeout)
        locator.click(force=force)

    def fill(self, selector: str, value: str, timeout: int = 5000) -> None:
        locator = self.wait_for_visible(selector, timeout)
        locator.fill(value)

    def get_text(self, selector: str, timeout: int = 5000) -> str:
        locator = self.wait_for_visible(selector, timeout)
        return locator.inner_text()

    def get_attribute(self, selector: str, attribute: str, timeout: int = 5000) -> Optional[str]:
        locator = self.wait_for_visible(selector, timeout)
        return locator.get_attribute(attribute)

    def is_visible(self, selector: str, timeout: int = 2000) -> bool:
        try:
            self.wait_for_visible(selector, timeout)
            return True
        except Exception:
            return False

    def is_hidden(self, selector: str, timeout: int = 2000) -> bool:
        try:
            self.wait_for_hidden(selector, timeout)
            return True
        except Exception:
            return False

    def wait_for_url(self, url: str, timeout: int = 30000) -> None:
        self.page.wait_for_url(url, timeout=timeout)

    def wait_for_navigation(self, timeout: int = 10000) -> None:
        self.page.wait_for_load_state("networkidle", timeout=timeout)

    def refresh(self) -> None:
        self.page.reload()

    def screenshot(self, path: str) -> None:
        self.page.screenshot(path=path)

    def wait(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000))

    def get_locator(self, selector: str) -> Locator:
        return self.page.locator(selector)

    def get_all_locators(self, selector: str) -> List[Locator]:
        locator = self.page.locator(selector)
        count = locator.count()
        return [locator.nth(i) for i in range(count)]

    def find_element_by_text(self, text: str, container_selector: str = "body") -> Optional[Locator]:
        container = self.page.locator(container_selector)
        elements = container.locator("*")
        for i in range(elements.count()):
            element = elements.nth(i)
            try:
                if element.inner_text() == text:
                    return element
            except Exception:
                continue
        return None

    def click_button_by_text(self, text: str, container_selector: str = "body") -> None:
        container = self.page.locator(container_selector)
        buttons = container.locator(f'button:has-text("{text}")')
        if buttons.count() > 0:
            buttons.first.click()
            return
        
        all_buttons = container.locator("button")
        for i in range(all_buttons.count()):
            button = all_buttons.nth(i)
            try:
                if text in button.inner_text():
                    button.click()
                    return
            except Exception:
                continue
        
        raise ValueError(f"Button with text '{text}' not found in container '{container_selector}'")

    def handle_dialog(self, accept: bool = True) -> None:
        self.page.on('dialog', lambda dialog: dialog.accept() if accept else dialog.dismiss())

    def execute_js(self, script: str, *args) -> any:
        return self.page.evaluate(script, *args)

    def scroll_into_view(self, selector: str) -> None:
        locator = self.page.locator(selector)
        locator.scroll_into_view_if_needed()

    def wait_for_network_idle(self, timeout: int = 10000) -> None:
        self.page.wait_for_load_state("networkidle", timeout=timeout)

    def wait_for_selector(self, selector: str, timeout: int = 5000) -> None:
        self.page.wait_for_selector(selector, timeout=timeout)

    def go_to(self, url: str) -> None:
        self.page.goto(url)

    def get_current_url(self) -> str:
        return self.page.url

    def wait_for_page_ready(self) -> None:
        self.page.wait_for_load_state("load")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_load_state("networkidle")

    def safe_click(self, selector: str, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
        for attempt in range(max_retries):
            try:
                self.click(selector)
                return True
            except Exception as e:
                self.logger.warning(f"Click attempt {attempt + 1} failed for selector '{selector}': {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        return False

    def safe_fill(self, selector: str, value: str, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
        for attempt in range(max_retries):
            try:
                self.fill(selector, value)
                return True
            except Exception as e:
                self.logger.warning(f"Fill attempt {attempt + 1} failed for selector '{selector}': {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        return False