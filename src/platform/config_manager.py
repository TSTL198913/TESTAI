import json
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfigSection:
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    readonly: bool = False


class ConfigManager:
    def __init__(self, config_file: str = None):
        self._config_file = config_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config",
            "platform_config.json",
        )
        self._sections: Dict[str, ConfigSection] = {}
        self._use_database = bool(os.environ.get("DATABASE_URL"))
        self._db = None
        if self._use_database:
            try:
                from src.storage.database import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"Database not available, falling back to JSON: {e}")
                self._use_database = False

        self._default_config = {
            "platform": {
                "name": "TestAI Platform",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO",
            },
            "api": {
                "host": "0.0.0.0",  # nosec B104 - intentional for container deployment
                "port": 8000,
                "cors_enabled": True,
                "docs_enabled": True,
            },
            "workflow": {
                "max_concurrent_workflows": 10,
                "task_timeout": 300,
                "retry_attempts": 3,
            },
            "governance": {
                "auto_approve_threshold": 0.95,
                "approval_required_for": ["SECURITY", "REFACTORING"],
                "max_patch_size": 1000,
            },
            "mutation_test": {
                "enabled": True,
                "target_dirs": ["src/governance/"],
                "kill_rate_threshold": 0.8,
            },
            "monitoring": {
                "alert_levels": ["INFO", "WARNING", "ERROR", "CRITICAL"],
                "auto_acknowledge_timeout": 3600,
                "health_check_interval": 60,
            },
        }
        self._load_config()

    def _load_config(self):
        if self._use_database and self._db:
            try:
                rows = self._db.select_all(self._db.system_config_table)
                if rows:
                    sections: Dict[str, Dict] = {}
                    for row in rows:
                        key = row["key"]
                        parts = key.split(".", 1)
                        section_name = parts[0]
                        config_key = parts[1] if len(parts) > 1 else ""

                        if section_name not in sections:
                            sections[section_name] = {
                                "data": {},
                                "description": row.get("description", ""),
                                "readonly": row.get("editable", True) is False,
                            }
                        if config_key:
                            try:
                                sections[section_name]["data"][config_key] = json.loads(row["value"])
                            except:
                                sections[section_name]["data"][config_key] = row["value"]

                    for name, section_data in sections.items():
                        self._sections[name] = ConfigSection(
                            name=name,
                            data=section_data.get("data", {}),
                            description=section_data.get("description", ""),
                            readonly=section_data.get("readonly", False),
                        )
                    return
            except Exception as e:
                logger.warning(f"Database load failed, using JSON: {e}")

        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, section_data in data.items():
                        self._sections[name] = ConfigSection(
                            name=name,
                            data=section_data.get("data", {}),
                            description=section_data.get("description", ""),
                            readonly=section_data.get("readonly", False),
                        )
            except Exception:
                self._load_defaults()
        else:
            self._load_defaults()

    def _load_defaults(self):
        for name, data in self._default_config.items():
            self._sections[name] = ConfigSection(name=name, data=data)

    def _save_config(self):
        if self._use_database and self._db:
            from datetime import datetime
            for name, section in self._sections.items():
                for key, value in section.data.items():
                    full_key = f"{name}.{key}"
                    try:
                        value_str = json.dumps(value)
                    except:
                        value_str = str(value)
                    existing = self._db.select_one(
                        self._db.system_config_table,
                        self._db.system_config_table.c.key == full_key
                    )
                    if existing:
                        self._db.update_many(
                            self._db.system_config_table,
                            self._db.system_config_table.c.key == full_key,
                            {
                                "value": value_str,
                                "description": section.description,
                                "editable": not section.readonly,
                                "updated_at": datetime.now(),
                            },
                        )
                    else:
                        self._db.insert_one(self._db.system_config_table, {
                            "key": full_key,
                            "value": value_str,
                            "description": section.description,
                            "category": name,
                            "editable": not section.readonly,
                        })
            return

        config_dir = os.path.dirname(self._config_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        data = {
            name: {
                "data": section.data,
                "description": section.description,
                "readonly": section.readonly,
            }
            for name, section in self._sections.items()
        }

        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_section(self, name: str) -> Optional[Dict[str, Any]]:
        section = self._sections.get(name)
        if not section:
            return None
        return {"name": section.name, "description": section.description, **section.data}

    def get_all(self) -> Dict[str, Any]:
        result = {}
        for name, section in self._sections.items():
            result[name] = {
                "description": section.description,
                "readonly": section.readonly,
                **section.data,
            }
        return result

    def update_section(self, name: str, data: Dict[str, Any]):
        section = self._sections.get(name)
        if not section:
            section = ConfigSection(name=name, data=data)
            self._sections[name] = section
        else:
            if section.readonly:
                raise PermissionError(f"Config section '{name}' is readonly")
            section.data.update(data)
        self._save_config()

    def set_value(self, section: str, key: str, value: Any):
        section_obj = self._sections.get(section)
        if not section_obj:
            section_obj = ConfigSection(name=section, data={})
            self._sections[section] = section_obj

        if section_obj.readonly:
            raise PermissionError(f"Config section '{section}' is readonly")

        section_obj.data[key] = value
        self._save_config()

    def get_value(self, section: str, key: str, default: Any = None) -> Any:
        section_obj = self._sections.get(section)
        if not section_obj:
            return default
        return section_obj.data.get(key, default)

    def add_section(self, name: str, data: Dict[str, Any] = None, description: str = "", readonly: bool = False):
        if name in self._sections:
            raise ValueError(f"Config section '{name}' already exists")

        self._sections[name] = ConfigSection(
            name=name,
            data=data or {},
            description=description,
            readonly=readonly,
        )
        self._save_config()

    def remove_section(self, name: str):
        if name not in self._sections:
            raise ValueError(f"Config section '{name}' does not exist")

        section = self._sections[name]
        if section.readonly:
            raise PermissionError(f"Config section '{name}' is readonly")

        del self._sections[name]
        self._save_config()

    def list_sections(self) -> list:
        return [
            {"name": name, "description": section.description, "readonly": section.readonly}
            for name, section in self._sections.items()
        ]