try:
    from playwright.sync_api import Page, expect, Locator
    _playwright_available = True
except ImportError:
    _playwright_available = False
    Page = None
    expect = None
    Locator = None
import logging
from typing import Optional, Any


class Assertions:
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger(self.__class__.__name__)

    def assert_element_visible(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_be_visible(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element visibility assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_visible_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should be visible") from e

    def assert_element_hidden(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_be_hidden(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element hidden assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_hidden_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should be hidden") from e

    def assert_element_exists(self, selector: str, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_have_count(lambda count: count > 0)
        except AssertionError as e:
            self.logger.error(f"Element existence assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_exists_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should exist") from e

    def assert_element_not_exists(self, selector: str, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_have_count(0)
        except AssertionError as e:
            self.logger.error(f"Element not existence assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_not_exists_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should not exist") from e

    def assert_text_visible(self, text: str, selector: str = "body", timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector).locator(f':has-text("{text}")')
            expect(locator).to_be_visible(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Text visibility assertion failed for text '{text}' in selector '{selector}': {e}")
            self._take_screenshot(f"assert_text_failure_{text[:20]}")
            raise AssertionError(message or f"Text '{text}' should be visible") from e

    def assert_text_not_visible(self, text: str, selector: str = "body", timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector).locator(f':has-text("{text}")')
            expect(locator).to_be_hidden(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Text not visibility assertion failed for text '{text}' in selector '{selector}': {e}")
            self._take_screenshot(f"assert_text_not_failure_{text[:20]}")
            raise AssertionError(message or f"Text '{text}' should not be visible") from e

    def assert_element_text(self, selector: str, expected_text: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_have_text(expected_text, timeout=timeout)
        except AssertionError as e:
            actual_text = ""
            try:
                actual_text = self.page.locator(selector).inner_text()
            except Exception:
                pass
            self.logger.error(f"Element text assertion failed for selector '{selector}': expected '{expected_text}', got '{actual_text}'")
            self._take_screenshot(f"assert_text_match_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should have text '{expected_text}', got '{actual_text}'") from e

    def assert_element_attribute(self, selector: str, attribute: str, expected_value: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_have_attribute(attribute, expected_value, timeout=timeout)
        except AssertionError as e:
            actual_value = ""
            try:
                actual_value = self.page.locator(selector).get_attribute(attribute)
            except Exception:
                pass
            self.logger.error(f"Element attribute assertion failed for selector '{selector}': expected {attribute}='{expected_value}', got '{actual_value}'")
            self._take_screenshot(f"assert_attr_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should have {attribute}='{expected_value}', got '{actual_value}'") from e

    def assert_url(self, expected_url: str, timeout: int = 30000, message: str = None) -> None:
        try:
            expect(self.page).to_have_url(expected_url, timeout=timeout)
        except AssertionError as e:
            current_url = self.page.url
            self.logger.error(f"URL assertion failed: expected '{expected_url}', got '{current_url}'")
            self._take_screenshot(f"assert_url_failure")
            raise AssertionError(message or f"URL should be '{expected_url}', got '{current_url}'") from e

    def assert_url_contains(self, expected_substring: str, timeout: int = 30000, message: str = None) -> None:
        # 关键: 必须用 Playwright 原生 wait_for_timeout 驱动事件循环,
        # 禁止用 time.sleep() —— sync API 下 time.sleep 不泵事件, page.url 返回过期快照,
        # 会漏掉客户端导航(如 router.push)导致永远读不到新 URL (暴露于 E2E 真实执行)
        import time
        start_time = time.time()
        while time.time() - start_time < timeout / 1000:
            current_url = self.page.url
            if expected_substring in current_url:
                return
            self.page.wait_for_timeout(100)

        current_url = self.page.url
        self.logger.error(f"URL contains assertion failed: expected substring '{expected_substring}', got '{current_url}'")
        self._take_screenshot(f"assert_url_contains_failure")
        raise AssertionError(message or f"URL should contain '{expected_substring}', got '{current_url}'")

    def assert_url_not_contains(self, substring: str, timeout: int = 5000, message: str = None) -> None:
        # 关键: 必须用 Playwright 原生 wait_for_timeout 驱动事件循环,
        # 禁止用 time.sleep() —— sync API 下 time.sleep 不泵事件, page.url 返回过期快照,
        # 会漏掉客户端导航(如 router.push)导致永远读不到新 URL (暴露于 E2E 真实执行)
        import time
        start_time = time.time()
        while time.time() - start_time < timeout / 1000:
            current_url = self.page.url
            if substring not in current_url:
                return
            self.page.wait_for_timeout(100)

        current_url = self.page.url
        self.logger.error(f"URL not contains assertion failed: URL should not contain '{substring}', got '{current_url}'")
        self._take_screenshot(f"assert_url_not_contains_failure")
        raise AssertionError(message or f"URL should not contain '{substring}', got '{current_url}'")

    def assert_element_count(self, selector: str, expected_count: int, message: str = None) -> None:
        try:
            if hasattr(selector, 'count'):
                locator = selector
            else:
                locator = self.page.locator(selector)
            expect(locator).to_have_count(expected_count)
        except AssertionError as e:
            if hasattr(selector, 'count'):
                actual_count = selector.count()
            else:
                actual_count = self.page.locator(selector).count()
            self.logger.error(f"Element count assertion failed: expected {expected_count}, got {actual_count}")
            self._take_screenshot(f"assert_count_failure")
            raise AssertionError(message or f"Element count should be {expected_count}, got {actual_count}") from e

    def assert_element_count_at_least(self, selector: str, min_count: int, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            actual_count = locator.count()
            if actual_count < min_count:
                raise AssertionError(f"Expected at least {min_count} elements, got {actual_count}")
        except AssertionError as e:
            actual_count = self.page.locator(selector).count()
            self.logger.error(f"Element count at least assertion failed for selector '{selector}': expected >= {min_count}, got {actual_count}")
            self._take_screenshot(f"assert_count_at_least_failure_{selector}")
            raise AssertionError(message or f"Element count for '{selector}' should be at least {min_count}, got {actual_count}") from e

    def assert_element_checked(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_be_checked(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element checked assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_checked_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should be checked") from e

    def assert_element_not_checked(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).not_to_be_checked(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element not checked assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_not_checked_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should not be checked") from e

    def assert_element_enabled(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_be_enabled(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element enabled assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_enabled_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should be enabled") from e

    def assert_element_disabled(self, selector: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_be_disabled(timeout=timeout)
        except AssertionError as e:
            self.logger.error(f"Element disabled assertion failed for selector '{selector}': {e}")
            self._take_screenshot(f"assert_disabled_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should be disabled") from e

    def assert_value(self, selector: str, expected_value: str, timeout: int = 5000, message: str = None) -> None:
        try:
            locator = self.page.locator(selector)
            expect(locator).to_have_value(expected_value, timeout=timeout)
        except AssertionError as e:
            actual_value = ""
            try:
                actual_value = self.page.locator(selector).input_value()
            except Exception:
                pass
            self.logger.error(f"Value assertion failed for selector '{selector}': expected '{expected_value}', got '{actual_value}'")
            self._take_screenshot(f"assert_value_failure_{selector}")
            raise AssertionError(message or f"Element '{selector}' should have value '{expected_value}', got '{actual_value}'") from e

    def assert_equal(self, actual: Any, expected: Any, message: str = None) -> None:
        if actual != expected:
            self.logger.error(f"Equal assertion failed: expected '{expected}', got '{actual}'")
            self._take_screenshot(f"assert_equal_failure")
            raise AssertionError(message or f"Expected '{expected}', got '{actual}'")

    def assert_not_equal(self, actual: Any, expected: Any, message: str = None) -> None:
        if actual == expected:
            self.logger.error(f"Not equal assertion failed: actual '{actual}' should not equal expected '{expected}'")
            self._take_screenshot(f"assert_not_equal_failure")
            raise AssertionError(message or f"'{actual}' should not equal '{expected}'")

    def assert_true(self, condition: bool, message: str = None) -> None:
        if not condition:
            self.logger.error(f"True assertion failed: condition is False")
            self._take_screenshot(f"assert_true_failure")
            raise AssertionError(message or "Expected condition to be True")

    def assert_false(self, condition: bool, message: str = None) -> None:
        if condition:
            self.logger.error(f"False assertion failed: condition is True")
            self._take_screenshot(f"assert_false_failure")
            raise AssertionError(message or "Expected condition to be False")

    def assert_in(self, item: Any, container: Any, message: str = None) -> None:
        if item not in container:
            self.logger.error(f"In assertion failed: '{item}' not in '{container}'")
            self._take_screenshot(f"assert_in_failure")
            raise AssertionError(message or f"'{item}' should be in '{container}'")

    def assert_not_in(self, item: Any, container: Any, message: str = None) -> None:
        if item in container:
            self.logger.error(f"Not in assertion failed: '{item}' is in '{container}'")
            self._take_screenshot(f"assert_not_in_failure")
            raise AssertionError(message or f"'{item}' should not be in '{container}'")

    def _take_screenshot(self, filename: str) -> None:
        try:
            safe_filename = filename.replace(":", "_").replace("/", "_").replace("\\", "_")
            self.page.screenshot(path=f"{safe_filename}.png")
        except Exception as e:
            self.logger.warning(f"Failed to take screenshot: {e}")