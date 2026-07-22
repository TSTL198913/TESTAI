import json
import os
from datetime import datetime
from typing import Optional

from src.governance.config import GovernanceConfig


class APIErrorRecorder:
    ERROR_LOG_PATH = "./logs/api_errors.json"

    @classmethod
    def _ensure_log_dir(cls):
        os.makedirs(os.path.dirname(cls.ERROR_LOG_PATH), exist_ok=True)

    @classmethod
    def record_error(
        cls,
        error_type: str,
        error_message: str,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_status: Optional[int] = None,
        additional_info: Optional[dict] = None,
    ):
        cls._ensure_log_dir()

        masked_key = None
        if api_key:
            masked_key = f"{api_key[:4]}***{api_key[-4:]}"

        error_record = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "api_key_masked": masked_key,
            "endpoint": endpoint,
            "http_status": http_status,
            "additional_info": additional_info or {},
            "testai_rule_13_compliant": GovernanceConfig.TESTAI_RULE_13,
            "complaint_ready": True,
        }

        try:
            if os.path.exists(cls.ERROR_LOG_PATH):
                with open(cls.ERROR_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            else:
                logs = []

            logs.append(error_record)

            with open(cls.ERROR_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)

            print(f"[TESTAI@13] ERROR RECORDED: {error_type} - {error_message}")
            return True

        except Exception as e:
            print(f"[TESTAI@13] Failed to record error: {e}")
            return False

    @classmethod
    def get_error_summary(cls) -> dict:
        cls._ensure_log_dir()

        if not os.path.exists(cls.ERROR_LOG_PATH):
            return {"total_errors": 0, "errors": []}

        with open(cls.ERROR_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)

        summary = {
            "total_errors": len(logs),
            "errors": logs,
            "by_type": {},
            "ready_for_complaint": [],
        }

        for log in logs:
            error_type = log.get("error_type", "unknown")
            if error_type not in summary["by_type"]:
                summary["by_type"][error_type] = 0
            summary["by_type"][error_type] += 1

            if log.get("complaint_ready", False):
                summary["ready_for_complaint"].append(log)

        return summary

    @classmethod
    def generate_complaint_report(cls) -> str:
        summary = cls.get_error_summary()

        if summary["total_errors"] == 0:
            return "No API errors recorded. All tests passed successfully."

        report = "=" * 80 + "\n"
        report += "TESTAI@13 - DEEPSEEK API COMPLAINT REPORT\n"
        report += "=" * 80 + "\n\n"
        report += f"Generated: {datetime.now().isoformat()}\n"
        report += f"Total Errors: {summary['total_errors']}\n"
        report += f"Rule 13 Compliant: {GovernanceConfig.TESTAI_RULE_13}\n\n"
        report += "Error Distribution:\n"
        report += "-" * 40 + "\n"

        for error_type, count in summary["by_type"].items():
            report += f"  {error_type}: {count} occurrences\n"

        report += "\nDetailed Error Records:\n"
        report += "-" * 40 + "\n"

        for i, error in enumerate(summary["errors"], 1):
            report += f"\n[{i}] {error['timestamp']}\n"
            report += f"   Type: {error['error_type']}\n"
            report += f"   Message: {error['error_message']}\n"
            if error.get("endpoint"):
                report += f"   Endpoint: {error['endpoint']}\n"
            if error.get("http_status"):
                report += f"   HTTP Status: {error['http_status']}\n"
            if error.get("api_key_masked"):
                report += f"   API Key: {error['api_key_masked']}\n"
            if error.get("additional_info"):
                report += f"   Additional: {json.dumps(error['additional_info'], ensure_ascii=False)}\n"

        report += "\n" + "=" * 80 + "\n"
        report += "COMPLAINT READY: YES\n"
        report += "=" * 80 + "\n"

        return report

    @classmethod
    def clear_errors(cls):
        cls._ensure_log_dir()
        if os.path.exists(cls.ERROR_LOG_PATH):
            os.remove(cls.ERROR_LOG_PATH)