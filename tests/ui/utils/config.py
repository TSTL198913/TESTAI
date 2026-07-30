import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UIConfig:
    base_url: str = field(default_factory=lambda: os.environ.get("BASE_URL", "http://localhost:3000"))
    api_base_url: str = field(default_factory=lambda: os.environ.get("API_BASE_URL", "http://localhost:8000"))
    browser_type: str = field(default_factory=lambda: os.environ.get("BROWSER_TYPE", "chromium"))
    headless: bool = field(default_factory=lambda: os.environ.get("HEADLESS", "true").lower() == "true")
    slow_mo: int = field(default_factory=lambda: int(os.environ.get("SLOW_MO", "100")))
    timeout: int = field(default_factory=lambda: int(os.environ.get("TIMEOUT", "30000")))
    page_timeout: int = field(default_factory=lambda: int(os.environ.get("PAGE_TIMEOUT", "60000")))
    retry_attempts: int = field(default_factory=lambda: int(os.environ.get("RETRY_ATTEMPTS", "3")))
    retry_delay: float = field(default_factory=lambda: float(os.environ.get("RETRY_DELAY", "1.0")))
    screenshot_on_failure: bool = field(default_factory=lambda: os.environ.get("SCREENSHOT_ON_FAILURE", "true").lower() == "true")
    video_on_failure: bool = field(default_factory=lambda: os.environ.get("VIDEO_ON_FAILURE", "false").lower() == "true")
    viewport_width: int = field(default_factory=lambda: int(os.environ.get("VIEWPORT_WIDTH", "1920")))
    viewport_height: int = field(default_factory=lambda: int(os.environ.get("VIEWPORT_HEIGHT", "1080")))

    def get_api_url(self) -> str:
        if self.api_base_url:
            return self.api_base_url
        return self.base_url.replace("3000", "8000") if "3000" in self.base_url else self.base_url

    def get_chrome_executable(self) -> Optional[str]:
        paths = [
            "C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return None

    def get_browser_args(self) -> list:
        return [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
        ]


config = UIConfig()