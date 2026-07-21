import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXECUTE = "execute"


class AuditResource(str, Enum):
    USER = "user"
    TEAM = "team"
    TEST_CASE = "test_case"
    TEST_RUN = "test_run"
    CONFIG = "config"
    REPORT = "report"
    API = "api"


@dataclass
class AuditLog:
    log_id: str
    user_id: str
    username: str
    action: AuditAction
    resource: AuditResource
    resource_id: str = ""
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error_message: str = ""


@dataclass
class SystemConfig:
    key: str
    value: str
    description: str = ""
    category: str = "general"
    editable: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class SystemOperations:
    def __init__(
        self,
        audit_log_path: str = None,
        config_path: str = None,
    ):
        self.audit_log_path = audit_log_path or os.environ.get(
            "AUDIT_LOG_PATH", "data/audit_logs.json"
        )
        self.config_path = config_path or os.environ.get(
            "SYSTEM_CONFIG_PATH", "data/system_config.json"
        )
        self.audit_logs: List[AuditLog] = []
        self.configs: Dict[str, SystemConfig] = {}
        self._load_audit_logs()
        self._load_configs()
        self._initialize_default_configs()

    def _load_audit_logs(self):
        if os.path.exists(self.audit_log_path):
            try:
                with open(self.audit_log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for log_data in data:
                        self.audit_logs.append(
                            AuditLog(
                                log_id=log_data["log_id"],
                                user_id=log_data["user_id"],
                                username=log_data["username"],
                                action=AuditAction(log_data["action"]),
                                resource=AuditResource(log_data["resource"]),
                                resource_id=log_data.get("resource_id", ""),
                                details=log_data.get("details", {}),
                                timestamp=datetime.fromisoformat(log_data["timestamp"]),
                                success=log_data.get("success", True),
                                error_message=log_data.get("error_message", ""),
                            )
                        )
            except Exception:
                self.audit_logs = []

    def _save_audit_logs(self):
        os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
        data = []
        for log in self.audit_logs[-10000:]:
            data.append(
                {
                    "log_id": log.log_id,
                    "user_id": log.user_id,
                    "username": log.username,
                    "action": log.action.value,
                    "resource": log.resource.value,
                    "resource_id": log.resource_id,
                    "details": log.details,
                    "timestamp": log.timestamp.isoformat(),
                    "success": log.success,
                    "error_message": log.error_message,
                }
            )
        with open(self.audit_log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_configs(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, config_data in data.items():
                        self.configs[key] = SystemConfig(
                            key=key,
                            value=config_data["value"],
                            description=config_data.get("description", ""),
                            category=config_data.get("category", "general"),
                            editable=config_data.get("editable", True),
                            created_at=datetime.fromisoformat(config_data["created_at"]),
                            updated_at=datetime.fromisoformat(config_data["updated_at"]),
                        )
            except Exception:
                self.configs = {}

    def _save_configs(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {}
        for key, config in self.configs.items():
            data[key] = {
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "category": config.category,
                "editable": config.editable,
                "created_at": config.created_at.isoformat(),
                "updated_at": config.updated_at.isoformat(),
            }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _initialize_default_configs(self):
        default_configs = [
            SystemConfig(
                key="system.name",
                value="TestAI",
                description="系统名称",
                category="system",
                editable=True,
            ),
            SystemConfig(
                key="system.version",
                value="1.0.0",
                description="系统版本",
                category="system",
                editable=False,
            ),
            SystemConfig(
                key="system.debug",
                value="false",
                description="调试模式",
                category="system",
                editable=True,
            ),
            SystemConfig(
                key="api.timeout",
                value="30",
                description="API请求超时时间（秒）",
                category="api",
                editable=True,
            ),
            SystemConfig(
                key="api.max_retries",
                value="3",
                description="API最大重试次数",
                category="api",
                editable=True,
            ),
            SystemConfig(
                key="ai.enabled",
                value="true",
                description="启用AI功能",
                category="ai",
                editable=True,
            ),
            SystemConfig(
                key="ai.fallback_enabled",
                value="true",
                description="启用AI降级方案",
                category="ai",
                editable=True,
            ),
            SystemConfig(
                key="test.default_timeout",
                value="60",
                description="测试默认超时时间（秒）",
                category="test",
                editable=True,
            ),
            SystemConfig(
                key="test.parallel_execution",
                value="false",
                description="启用并行执行",
                category="test",
                editable=True,
            ),
            SystemConfig(
                key="logging.level",
                value="INFO",
                description="日志级别",
                category="logging",
                editable=True,
            ),
        ]

        for config in default_configs:
            if config.key not in self.configs:
                self.configs[config.key] = config

        self._save_configs()

    def log_audit(
        self,
        user_id: str,
        username: str,
        action: AuditAction,
        resource: AuditResource,
        resource_id: str = "",
        details: Dict = None,
        success: bool = True,
        error_message: str = "",
    ):
        log_id = f"log_{len(self.audit_logs) + 1:06d}"
        log = AuditLog(
            log_id=log_id,
            user_id=user_id,
            username=username,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details or {},
            timestamp=datetime.now(),
            success=success,
            error_message=error_message,
        )
        self.audit_logs.append(log)
        self._save_audit_logs()
        return log

    def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource: Optional[AuditResource] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        filtered = []
        for log in self.audit_logs:
            if user_id and log.user_id != user_id:
                continue
            if action and log.action != action:
                continue
            if resource and log.resource != resource:
                continue
            if start_time and log.timestamp < start_time:
                continue
            if end_time and log.timestamp > end_time:
                continue
            filtered.append(log)

        filtered.sort(key=lambda x: x.timestamp, reverse=True)

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = filtered[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": paginated,
        }

    def get_config(self, key: str) -> Optional[SystemConfig]:
        return self.configs.get(key)

    def get_config_value(self, key: str, default: str = "") -> str:
        config = self.configs.get(key)
        return config.value if config else default

    def set_config(
        self,
        key: str,
        value: str,
        description: str = "",
        category: str = "general",
    ) -> SystemConfig:
        if key in self.configs:
            config = self.configs[key]
            if not config.editable:
                raise ValueError(f"Config '{key}' is not editable")
            config.value = value
            if description:
                config.description = description
            if category:
                config.category = category
            config.updated_at = datetime.now()
        else:
            config = SystemConfig(
                key=key,
                value=value,
                description=description,
                category=category,
                editable=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self.configs[key] = config

        self._save_configs()
        return config

    def delete_config(self, key: str) -> bool:
        if key in self.configs:
            if not self.configs[key].editable:
                raise ValueError(f"Config '{key}' is not deletable")
            del self.configs[key]
            self._save_configs()
            return True
        return False

    def list_configs(self, category: Optional[str] = None) -> List[SystemConfig]:
        filtered = []
        for config in self.configs.values():
            if category and config.category != category:
                continue
            filtered.append(config)
        return sorted(filtered, key=lambda c: c.key)

    def get_system_status(self) -> Dict:
        return {
            "status": "healthy",
            "version": self.get_config_value("system.version", "1.0.0"),
            "config_count": len(self.configs),
            "audit_log_count": len(self.audit_logs),
            "ai_enabled": self.get_config_value("ai.enabled", "false") == "true",
            "debug_mode": self.get_config_value("system.debug", "false") == "true",
            "timestamp": datetime.now().isoformat(),
        }

    def count_audit_logs(self) -> Dict[str, int]:
        counts = {"total": len(self.audit_logs)}
        for action in AuditAction:
            counts[f"action_{action.value}"] = sum(
                1 for log in self.audit_logs if log.action == action
            )
        for resource in AuditResource:
            counts[f"resource_{resource.value}"] = sum(
                1 for log in self.audit_logs if log.resource == resource
            )
        counts["failed"] = sum(1 for log in self.audit_logs if not log.success)
        return counts