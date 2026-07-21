# src/storage/database.py
"""数据库抽象层 - 支持 SQLite(开发) 和 PostgreSQL(生产)"""
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Text, Integer, Boolean, DateTime, JSON,
    MetaData, Table, select, insert, update, delete, func
)
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """从环境变量获取数据库URL，默认使用SQLite"""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    db_path = os.environ.get("SQLITE_PATH", "data/testai.db")
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    return f"sqlite:///{db_path}"


class DatabaseManager:
    """数据库管理器 - 提供统一的表操作接口"""

    _instance: Optional["DatabaseManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, database_url: str = None):
        if hasattr(self, "_initialized"):
            return
        self.database_url = database_url or get_database_url()
        self.engine: Engine = create_engine(
            self.database_url,
            echo=False,
            connect_args={"check_same_thread": False}
            if self.database_url.startswith("sqlite")
            else {},
        )
        self.metadata = MetaData()
        self._define_tables()
        self.metadata.create_all(self.engine)
        self._initialized = True

    def _define_tables(self):
        """定义所有表结构"""
        self.users_table = Table(
            "users", self.metadata,
            Column("user_id", String(64), primary_key=True),
            Column("username", String(128), unique=True, nullable=False),
            Column("email", String(256), unique=True, nullable=False),
            Column("password_hash", String(256), nullable=True),
            Column("role", String(32), nullable=False),
            Column("status", String(32), nullable=False, default="active"),
            Column("full_name", String(128), default=""),
            Column("department", String(128), default=""),
            Column("avatar_url", String(512), default=""),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("last_login_at", DateTime, nullable=True),
            Column("metadata", JSON, default={}),
        )

        self.teams_table = Table(
            "teams", self.metadata,
            Column("team_id", String(64), primary_key=True),
            Column("name", String(128), unique=True, nullable=False),
            Column("description", Text, default=""),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("updated_at", DateTime, default=datetime.utcnow),
            Column("metadata", JSON, default={}),
        )

        self.team_members_table = Table(
            "team_members", self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("team_id", String(64), nullable=False),
            Column("user_id", String(64), nullable=False),
            Column("username", String(128), nullable=False),
            Column("role", String(32), nullable=False, default="member"),
            Column("joined_at", DateTime, default=datetime.utcnow),
        )

        self.audit_logs_table = Table(
            "audit_logs", self.metadata,
            Column("log_id", String(64), primary_key=True),
            Column("user_id", String(64), nullable=False),
            Column("username", String(128), nullable=False),
            Column("action", String(32), nullable=False),
            Column("resource", String(32), nullable=False),
            Column("resource_id", String(64), default=""),
            Column("details", JSON, default={}),
            Column("timestamp", DateTime, default=datetime.utcnow),
            Column("success", Boolean, default=True),
            Column("error_message", Text, default=""),
        )

        self.system_config_table = Table(
            "system_config", self.metadata,
            Column("key", String(128), primary_key=True),
            Column("value", Text, nullable=False),
            Column("description", Text, default=""),
            Column("category", String(64), default="general"),
            Column("editable", Boolean, default=True),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("updated_at", DateTime, default=datetime.utcnow),
        )

        self.alerts_table = Table(
            "alerts", self.metadata,
            Column("alert_id", String(64), primary_key=True),
            Column("level", String(32), nullable=False),
            Column("alert_type", String(64), nullable=False),
            Column("title", String(256), nullable=False),
            Column("message", Text, nullable=False),
            Column("source", String(128), default=""),
            Column("status", String(32), nullable=False, default="open"),
            Column("details", JSON, default={}),
            Column("timestamp", DateTime, default=datetime.utcnow),
            Column("acknowledged_by", String(64), nullable=True),
            Column("acknowledged_at", DateTime, nullable=True),
            Column("resolved_by", String(64), nullable=True),
            Column("resolved_at", DateTime, nullable=True),
        )

        self.notifications_table = Table(
            "notifications", self.metadata,
            Column("notification_id", String(64), primary_key=True),
            Column("channel", String(32), nullable=False),
            Column("recipient", String(256), nullable=False),
            Column("title", String(256), nullable=False),
            Column("message", Text, nullable=False),
            Column("status", String(32), default="pending"),
            Column("error_message", Text, default=""),
            Column("sent_at", DateTime, nullable=True),
        )

        self.workflows_table = Table(
            "workflows", self.metadata,
            Column("workflow_id", String(64), primary_key=True),
            Column("name", String(256), nullable=False),
            Column("description", Text, default=""),
            Column("tasks", JSON, default=[]),
            Column("triggers", JSON, default={}),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("updated_at", DateTime, default=datetime.utcnow),
        )

        self.workflow_instances_table = Table(
            "workflow_instances", self.metadata,
            Column("instance_id", String(64), primary_key=True),
            Column("workflow_id", String(64), nullable=False),
            Column("status", String(32), nullable=False),
            Column("tasks", JSON, default={}),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("started_at", DateTime, nullable=True),
            Column("completed_at", DateTime, nullable=True),
            Column("error", Text, nullable=True),
        )

    def execute_query(self, query):
        """执行查询并返回结果"""
        with self.engine.connect() as conn:
            if isinstance(query, str):
                from sqlalchemy import text
                return conn.execute(text(query))
            result = conn.execute(query)
            conn.commit()
            return result

    def insert_one(self, table, data: Dict) -> bool:
        """插入一条记录"""
        with self.engine.connect() as conn:
            conn.execute(insert(table).values(**data))
            conn.commit()
            return True

    def update_many(self, table, where_clause, values: Dict) -> int:
        """更新记录"""
        with self.engine.connect() as conn:
            result = conn.execute(update(table).where(where_clause).values(**values))
            conn.commit()
            return result.rowcount

    def delete_many(self, table, where_clause) -> int:
        """删除记录"""
        with self.engine.connect() as conn:
            result = conn.execute(delete(table).where(where_clause))
            conn.commit()
            return result.rowcount

    def select_one(self, table, where_clause=None) -> Optional[Dict]:
        """查询单条记录"""
        with self.engine.connect() as conn:
            query = select(table)
            if where_clause is not None:
                query = query.where(where_clause)
            result = conn.execute(query)
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None

    def select_all(self, table, where_clause=None, limit: int = None) -> List[Dict]:
        """查询多条记录"""
        with self.engine.connect() as conn:
            query = select(table)
            if where_clause is not None:
                query = query.where(where_clause)
            if limit:
                query = query.limit(limit)
            result = conn.execute(query)
            return [dict(row._mapping) for row in result.fetchall()]

    def count(self, table, where_clause=None) -> int:
        """计数"""
        with self.engine.connect() as conn:
            query = select(func.count()).select_from(table)
            if where_clause is not None:
                query = query.where(where_clause)
            result = conn.execute(query)
            return result.scalar()

    def reset(self):
        """重置数据库（仅用于测试）"""
        self.metadata.drop_all(self.engine)
        self.metadata.create_all(self.engine)


# 全局单例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def reset_db_manager():
    """重置数据库管理器单例（仅用于测试）"""
    global _db_manager
    _db_manager = None
