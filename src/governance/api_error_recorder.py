import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from src.governance.config import GovernanceConfig


class APIErrorRecorder:
    ERROR_LOG_PATH = "./logs/api_errors.json"
    # P5 修复: RMW (read-modify-write) 必须持锁, 避免并发
    # last-writer-wins 数据丢失 (规则13 投诉证据链断裂)。
    # 使用 RLock 允许同线程内重入 (如 generate_complaint_report -> get_error_summary)。
    _lock = threading.RLock()
    _logger = logging.getLogger("APIErrorRecorder")

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

        # P5 修复: 持锁执行完整 RMW (读-改-写), 任意并发调用串行化,
        # 杜绝 last-writer-wins 数据丢失。
        with cls._lock:
            # READ: 容忍损坏 JSON (重建为空列表), 保留已有合法记录
            logs = []
            if os.path.exists(cls.ERROR_LOG_PATH):
                try:
                    with open(cls.ERROR_LOG_PATH, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                    if not isinstance(logs, list):
                        cls._logger.warning(
                            "API error log not a list (type=%s), rebuilding",
                            type(logs).__name__,
                        )
                        logs = []
                except json.JSONDecodeError as e:
                    cls._logger.warning(
                        "API error log corrupted, rebuilding: %s (type=%s)",
                        e, type(e).__name__,
                    )
                    logs = []
                except OSError as e:
                    cls._logger.error(
                        "Failed to read API error log (type=%s): %s",
                        error_type, e,
                        exc_info=True,
                    )
                    return False

            # MODIFY
            logs.append(error_record)

            # WRITE
            try:
                with open(cls.ERROR_LOG_PATH, "w", encoding="utf-8") as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
            except OSError as e:
                cls._logger.error(
                    "Failed to write API error log (type=%s): %s",
                    error_type, e,
                    exc_info=True,
                )
                return False

        cls._logger.info(
            "[TESTAI@13] ERROR RECORDED: %s - %s", error_type, error_message
        )
        return True

    @classmethod
    def get_error_summary(cls) -> dict:
        cls._ensure_log_dir()

        # P5 修复: 持锁读取, 避免并发 record_error 写入时读到半写 JSON。
        with cls._lock:
            logs = []
            if os.path.exists(cls.ERROR_LOG_PATH):
                try:
                    with open(cls.ERROR_LOG_PATH, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                    if not isinstance(logs, list):
                        cls._logger.warning(
                            "API error log not a list (type=%s), treating as empty",
                            type(logs).__name__,
                        )
                        logs = []
                except json.JSONDecodeError as e:
                    cls._logger.warning(
                        "API error log corrupted: %s (type=%s)", e, type(e).__name__
                    )
                    logs = []
                except OSError as e:
                    cls._logger.error(
                        "Failed to read API error log: %s (type=%s)",
                        e, type(e).__name__,
                        exc_info=True,
                    )
                    logs = []

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
        # P5 修复: 持锁删除, 避免与并发 record_error 竞争导致 OSError。
        with cls._lock:
            if os.path.exists(cls.ERROR_LOG_PATH):
                try:
                    os.remove(cls.ERROR_LOG_PATH)
                except OSError as e:
                    cls._logger.error(
                        "Failed to clear API error log: %s (type=%s)",
                        e, type(e).__name__,
                        exc_info=True,
                    )
