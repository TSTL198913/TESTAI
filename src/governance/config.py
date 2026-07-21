import os

from dotenv import load_dotenv

load_dotenv()


class GovernanceConfig:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    GOVERNANCE_DB_PATH = os.getenv("GOVERNANCE_DB_PATH", "./data/governance.sqlite")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
    MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "5"))
    APPROVAL_EXPIRY_MINUTES = int(os.getenv("APPROVAL_EXPIRY_MINUTES", "30"))
    CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "3"))
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(
        os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "30")
    )
    USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "false").lower() == "true"

    TESTAI_RULE_13 = os.getenv("TESTAI_RULE_13", "true").lower() == "true"

    @classmethod
    def is_llm_configured(cls) -> bool:
        return bool(cls.DEEPSEEK_API_KEY)

    @classmethod
    def is_alert_configured(cls) -> bool:
        return bool(cls.ALERT_WEBHOOK_URL)

    @classmethod
    def validate_api_key(cls) -> dict:
        result = {
            "valid": False,
            "message": "",
            "key_length": len(cls.DEEPSEEK_API_KEY),
            "compliant_with_rule_13": False,
        }
        
        if not cls.DEEPSEEK_API_KEY:
            result["message"] = "DEEPSEEK_API_KEY is not set"
            return result
            
        if not cls.DEEPSEEK_API_KEY.startswith("sk-"):
            result["message"] = "API key format is invalid (should start with 'sk-')"
            return result
            
        if len(cls.DEEPSEEK_API_KEY) < 20:
            result["message"] = "API key is too short (minimum 20 characters required)"
            return result
            
        if cls.TESTAI_RULE_13 and cls.USE_MOCK_LLM:
            result["message"] = "TESTAI@13 violation: USE_MOCK_LLM is enabled but should use real API key"
            return result
            
        result["valid"] = True
        result["compliant_with_rule_13"] = True
        result["message"] = "API key format is valid and compliant with TESTAI@13"
        return result

    @classmethod
    def get_config_summary(cls) -> dict:
        api_key_validation = cls.validate_api_key()
        return {
            "llm_configured": cls.is_llm_configured(),
            "api_key_valid": api_key_validation["valid"],
            "api_key_message": api_key_validation["message"],
            "compliant_with_rule_13": api_key_validation["compliant_with_rule_13"],
            "alert_configured": cls.is_alert_configured(),
            "db_path": cls.GOVERNANCE_DB_PATH,
            "log_level": cls.LOG_LEVEL,
            "max_concurrent_llm_calls": cls.MAX_CONCURRENT_LLM_CALLS,
            "approval_expiry_minutes": cls.APPROVAL_EXPIRY_MINUTES,
            "use_mock_llm": cls.USE_MOCK_LLM,
            "testai_rule_13_enabled": cls.TESTAI_RULE_13,
        }