import logging
import os
from datetime import datetime


class TestLogger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._logger = logging.getLogger("ui_test")
        self._logger.setLevel(logging.INFO)
        
        if not self._logger.handlers:
            log_dir = "test_logs"
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_handler = logging.FileHandler(f"{log_dir}/ui_test_{timestamp}.log", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
            
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self._logger.addHandler(file_handler)
            self._logger.addHandler(console_handler)
        
        self._initialized = True

    def get_logger(self, name: str = None) -> logging.Logger:
        if name:
            return logging.getLogger(name)
        return self._logger

    def info(self, message: str) -> None:
        self._logger.info(message)

    def debug(self, message: str) -> None:
        self._logger.debug(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(self, message: str) -> None:
        self._logger.error(message)

    def critical(self, message: str) -> None:
        self._logger.critical(message)

    def log_test_start(self, test_name: str) -> None:
        self.info(f"{'='*60}")
        self.info(f"TEST START: {test_name}")
        self.info(f"{'='*60}")

    def log_test_end(self, test_name: str, passed: bool, duration: float = None) -> None:
        status = "PASSED" if passed else "FAILED"
        duration_str = f" | Duration: {duration:.2f}s" if duration else ""
        self.info(f"{'='*60}")
        self.info(f"TEST END: {test_name} | Status: {status}{duration_str}")
        self.info(f"{'='*60}")

    def log_step(self, step: str, description: str = "") -> None:
        self.info(f"[STEP] {step}: {description}")

    def log_assertion(self, assertion: str, passed: bool, details: str = "") -> None:
        status = "✓" if passed else "✗"
        self.info(f"[ASSERT] {status} {assertion}{' | ' + details if details else ''}")

    def log_error_details(self, error: Exception, context: str = "") -> None:
        self.error(f"Error in {context}: {type(error).__name__} - {error}")


test_logger = TestLogger()