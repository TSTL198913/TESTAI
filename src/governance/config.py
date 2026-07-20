import os

from dotenv import load_dotenv

load_dotenv()


class GovernanceConfig:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    GOVERNANCE_DB_PATH = os.getenv("GOVERNANCE_DB_PATH", "./data/governance.sqlite")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
    MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "5"))
    APPROVAL_EXPIRY_MINUTES = int(os.getenv("APPROVAL_EXPIRY_MINUTES", "30"))
    CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "3"))
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(
        os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "30")
    )

    @classmethod
    def is_llm_configured(cls) -> bool:
        return bool(cls.DEEPSEEK_API_KEY)

    @classmethod
    def is_alert_configured(cls) -> bool:
        return bool(cls.ALERT_WEBHOOK_URL)

    @classmethod
    def get_config_summary(cls) -> dict:
        return {
            "llm_configured": cls.is_llm_configured(),
            "alert_configured": cls.is_alert_configured(),
            "db_path": cls.GOVERNANCE_DB_PATH,
            "log_level": cls.LOG_LEVEL,
            "max_concurrent_llm_calls": cls.MAX_CONCURRENT_LLM_CALLS,
            "approval_expiry_minutes": cls.APPROVAL_EXPIRY_MINUTES,
        }
