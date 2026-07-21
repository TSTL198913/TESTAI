import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from src.security.auth import User, Role as UserRole, PasswordHasher

logger = logging.getLogger(__name__)


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


@dataclass
class UserProfile:
    user_id: str
    username: str
    email: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    full_name: str = ""
    department: str = ""
    avatar_url: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_login_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)
    password_hash: str = ""


class UserManager:
    def __init__(self, storage_path: str = None, use_database: bool = None):
        self.storage_path = storage_path or os.environ.get(
            "USER_STORAGE_PATH", "data/users.json"
        )
        self.users: Dict[str, UserProfile] = {}
        self._use_database = use_database if use_database is not None else bool(
            os.environ.get("DATABASE_URL")
        )
        self._db = None
        if self._use_database:
            try:
                from src.storage.database import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"Database not available, falling back to JSON: {e}")
                self._use_database = False

        self._load_users()
        self._initialize_default_users()

    def _load_users(self):
        if self._use_database and self._db:
            try:
                rows = self._db.select_all(self._db.users_table)
                for row in rows:
                    user = UserProfile(
                        user_id=row["user_id"],
                        username=row["username"],
                        email=row["email"],
                        role=UserRole(row["role"]),
                        status=UserStatus(row["status"]),
                        full_name=row.get("full_name", ""),
                        department=row.get("department", ""),
                        avatar_url=row.get("avatar_url", ""),
                        created_at=row.get("created_at", datetime.now()),
                        last_login_at=row.get("last_login_at"),
                        metadata=row.get("metadata", {}),
                        password_hash=row.get("password_hash", ""),
                    )
                    self.users[user.user_id] = user
                return
            except Exception as e:
                logger.warning(f"Database load failed, using JSON: {e}")

        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for user_id, user_data in data.items():
                        self.users[user_id] = UserProfile(
                            user_id=user_data["user_id"],
                            username=user_data["username"],
                            email=user_data["email"],
                            role=UserRole(user_data["role"]),
                            status=UserStatus(user_data["status"]),
                            full_name=user_data.get("full_name", ""),
                            department=user_data.get("department", ""),
                            avatar_url=user_data.get("avatar_url", ""),
                            created_at=datetime.fromisoformat(user_data["created_at"]),
                            last_login_at=datetime.fromisoformat(user_data["last_login_at"])
                            if user_data.get("last_login_at")
                            else None,
                            metadata=user_data.get("metadata", {}),
                            password_hash=user_data.get("password_hash", ""),
                        )
            except Exception:
                self.users = {}

    def _save_users(self):
        if self._use_database and self._db:
            return
        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        data = {}
        for user_id, user in self.users.items():
            data[user_id] = {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "status": user.status.value,
                "full_name": user.full_name,
                "department": user.department,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat(),
                "last_login_at": user.last_login_at.isoformat()
                if user.last_login_at
                else None,
                "metadata": user.metadata,
                "password_hash": user.password_hash,
            }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _initialize_default_users(self):
        if not self.users:
            self.create_user(
                username="admin",
                email="admin@testai.local",
                role=UserRole.ADMIN,
                full_name="系统管理员",
                department="技术部",
            )
            self.create_user(
                username="tester",
                email="tester@testai.local",
                role=UserRole.TESTER,
                full_name="测试工程师",
                department="测试部",
            )
            self.create_user(
                username="viewer",
                email="viewer@testai.local",
                role=UserRole.VIEWER,
                full_name="查看用户",
                department="产品部",
            )

    def create_user(
        self,
        username: str,
        email: str,
        role: UserRole,
        full_name: str = "",
        department: str = "",
        status: UserStatus = UserStatus.ACTIVE,
        password: str = "",
    ) -> UserProfile:
        if username in [u.username for u in self.users.values()]:
            raise ValueError(f"Username '{username}' already exists")
        if email in [u.email for u in self.users.values()]:
            raise ValueError(f"Email '{email}' already exists")

        user_id = f"user_{len(self.users) + 1:04d}"
        password_hash = PasswordHasher.hash_password(password) if password else ""
        user = UserProfile(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            status=status,
            full_name=full_name,
            department=department,
            created_at=datetime.now(),
            password_hash=password_hash,
        )
        self.users[user_id] = user

        if self._use_database and self._db:
            self._db.insert_one(self._db.users_table, {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "password_hash": password_hash,
                "role": user.role.value,
                "status": user.status.value,
                "full_name": user.full_name,
                "department": user.department,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
                "metadata": user.metadata,
            })
        else:
            self._save_users()
        return user

    def get_user(self, user_id: str) -> Optional[UserProfile]:
        return self.users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[UserProfile]:
        for user in self.users.values():
            if user.username == username:
                return user
        return None

    def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        for user in self.users.values():
            if user.email == email:
                return user
        return None

    def verify_password(self, username: str, password: str) -> bool:
        """验证用户密码"""
        user = self.get_user_by_username(username)
        if not user or not user.password_hash:
            return False
        return PasswordHasher.verify_password(password, user.password_hash)

    def set_password(self, user_id: str, password: str) -> bool:
        """设置用户密码"""
        user = self.users.get(user_id)
        if not user:
            return False
        user.password_hash = PasswordHasher.hash_password(password)
        if self._use_database and self._db:
            self._db.update_many(
                self._db.users_table,
                self._db.users_table.c.user_id == user_id,
                {"password_hash": user.password_hash},
            )
        else:
            self._save_users()
        return True

    def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        full_name: Optional[str] = None,
        department: Optional[str] = None,
        avatar_url: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[UserProfile]:
        user = self.users.get(user_id)
        if not user:
            return None

        if username:
            existing = self.get_user_by_username(username)
            if existing and existing.user_id != user_id:
                raise ValueError(f"Username '{username}' already exists")
            user.username = username

        if email:
            existing = self.get_user_by_email(email)
            if existing and existing.user_id != user_id:
                raise ValueError(f"Email '{email}' already exists")
            user.email = email

        if role:
            user.role = role
        if status:
            user.status = status
        if full_name is not None:
            user.full_name = full_name
        if department is not None:
            user.department = department
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if metadata is not None:
            user.metadata = metadata

        if self._use_database and self._db:
            self._db.update_many(
                self._db.users_table,
                self._db.users_table.c.user_id == user_id,
                {
                    "username": user.username,
                    "email": user.email,
                    "role": user.role.value,
                    "status": user.status.value,
                    "full_name": user.full_name,
                    "department": user.department,
                    "avatar_url": user.avatar_url,
                    "metadata": user.metadata,
                },
            )
        else:
            self._save_users()
        return user

    def delete_user(self, user_id: str) -> bool:
        if user_id in self.users:
            del self.users[user_id]
            if self._use_database and self._db:
                self._db.delete_many(
                    self._db.users_table,
                    self._db.users_table.c.user_id == user_id,
                )
            else:
                self._save_users()
            return True
        return False

    def list_users(
        self,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        department: Optional[str] = None,
    ) -> List[UserProfile]:
        filtered = []
        for user in self.users.values():
            if role and user.role != role:
                continue
            if status and user.status != status:
                continue
            if department and user.department != department:
                continue
            filtered.append(user)
        return sorted(filtered, key=lambda u: u.created_at, reverse=True)

    def update_last_login(self, user_id: str):
        user = self.users.get(user_id)
        if user:
            user.last_login_at = datetime.now()
            if self._use_database and self._db:
                self._db.update_many(
                    self._db.users_table,
                    self._db.users_table.c.user_id == user_id,
                    {"last_login_at": user.last_login_at},
                )
            else:
                self._save_users()

    def activate_user(self, user_id: str) -> Optional[UserProfile]:
        return self.update_user(user_id, status=UserStatus.ACTIVE)

    def suspend_user(self, user_id: str) -> Optional[UserProfile]:
        return self.update_user(user_id, status=UserStatus.SUSPENDED)

    def deactivate_user(self, user_id: str) -> Optional[UserProfile]:
        return self.update_user(user_id, status=UserStatus.INACTIVE)

    def count_users(self) -> Dict[str, int]:
        counts = {"total": len(self.users)}
        for role in UserRole:
            counts[f"role_{role.value}"] = sum(
                1 for u in self.users.values() if u.role == role
            )
        for status in UserStatus:
            counts[f"status_{status.value}"] = sum(
                1 for u in self.users.values() if u.status == status
            )
        return counts