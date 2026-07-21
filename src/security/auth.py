import os
import jwt
import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

# bcrypt 可选导入（生产环境推荐使用）
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt not installed, using PBKDF2 fallback")


class Role(str, Enum):
    ADMIN = "admin"
    TESTER = "tester"
    VIEWER = "viewer"
    GUEST = "guest"


@dataclass
class User:
    id: str
    username: str
    email: str
    role: Role
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    password_hash: str = ""


class PasswordHasher:
    """密码哈希工具 - 支持 bcrypt 和 PBKDF2 降级方案"""

    @staticmethod
    def hash_password(password: str) -> str:
        """哈希密码"""
        if not password:
            return ""
        if BCRYPT_AVAILABLE:
            # bcrypt 限制密码长度为72字节
            password_bytes = password.encode("utf-8")[:72]
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password_bytes, salt).decode("utf-8")
        # PBKDF2 降级方案
        salt = secrets.token_hex(16)
        iterations = 100000
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return f"pbkdf2${iterations}${salt}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        if not password or not password_hash:
            return False
        if BCRYPT_AVAILABLE and not password_hash.startswith("pbkdf2$"):
            try:
                # bcrypt 限制密码长度为72字节
                password_bytes = password.encode("utf-8")[:72]
                return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
            except Exception:
                return False
        # PBKDF2 验证
        if password_hash.startswith("pbkdf2$"):
            parts = password_hash.split("$")
            if len(parts) != 4:
                return False
            _, iterations, salt, stored_hash = parts
            iterations = int(iterations)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
            return hmac.compare_digest(dk.hex(), stored_hash)
        return False


class TokenManager:
    def __init__(self, secret_key: Optional[str] = None, algorithm: str = "HS256"):
        self.secret_key = self._get_or_generate_secret_key(secret_key)
        self.algorithm = algorithm
        self.access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.refresh_token_expire_days = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        self.users: Dict[str, User] = {}
        self._password_hashes: Dict[str, str] = {}
        self._initialize_default_users()

    def _get_or_generate_secret_key(self, provided_key: Optional[str]) -> str:
        """获取或生成密钥 - 优先从环境变量，无则生成临时密钥并警告"""
        key = provided_key or os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET_KEY")
        if key:
            if len(key) < 32:
                raise ValueError(
                    "JWT secret key must be at least 32 bytes (256 bits). "
                    "Set SECRET_KEY environment variable with a 32+ byte key."
                )
            return key
        # 开发模式：生成临时密钥
        generated = secrets.token_hex(32)
        logger.warning(
            "No SECRET_KEY found in environment variables. "
            "Generated a temporary key for development. "
            "Set SECRET_KEY environment variable for production."
        )
        return generated

    def _initialize_default_users(self):
        default_users = [
            User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN),
            User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER),
            User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER),
        ]
        default_password = os.environ.get("DEFAULT_USER_PASSWORD", "password")
        for user in default_users:
            self.users[user.username] = user
            self._password_hashes[user.username] = PasswordHasher.hash_password(default_password)

    def create_access_token(self, user: User) -> str:
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role.value,
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user: User) -> str:
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        payload = {
            "sub": user.id,
            "username": user.username,
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def verify_token(self, token: str) -> Optional[User]:
        payload = self.decode_token(token)
        if not payload:
            return None

        if payload.get("type") != "access":
            return None

        username = payload.get("username")
        user = self.users.get(username)

        if user and user.is_active:
            user.last_login = datetime.now()
            return user

        return None

    def refresh_token(self, refresh_token: str) -> Optional[str]:
        payload = self.decode_token(refresh_token)
        if not payload:
            return None

        if payload.get("type") != "refresh":
            return None

        username = payload.get("username")
        user = self.users.get(username)

        if user and user.is_active:
            return self.create_access_token(user)

        return None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.users.get(username)
        if not user or not user.is_active:
            return None

        stored_hash = self._password_hashes.get(username, "")
        if PasswordHasher.verify_password(password, stored_hash):
            user.last_login = datetime.now()
            return user
        return None

    def set_password(self, username: str, password: str):
        """设置用户密码"""
        self._password_hashes[username] = PasswordHasher.hash_password(password)

    def get_password_hash(self, username: str) -> str:
        """获取密码哈希"""
        return self._password_hashes.get(username, "")