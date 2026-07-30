import os
import jwt
import hashlib
import hmac
import secrets
import logging
import threading
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
            password_bytes = password.encode("utf-8")[:72]
            bcrypt_salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password_bytes, bcrypt_salt).decode("utf-8")
        salt_str = secrets.token_hex(16)
        iterations = 100000
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_str.encode("utf-8"), iterations)
        return f"pbkdf2${iterations}${salt_str}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        if not password or not password_hash:
            return False
        if BCRYPT_AVAILABLE and not password_hash.startswith("pbkdf2$"):
            try:
                password_bytes = password.encode("utf-8")[:72]
                return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
            except Exception as e:
                logger.warning(f"Password verification failed: {type(e).__name__}: {e}")
                return False
        # PBKDF2 验证
        if password_hash.startswith("pbkdf2$"):
            parts = password_hash.split("$")
            if len(parts) != 4:
                return False
            _, iterations_str, salt, stored_hash = parts
            iterations = int(iterations_str)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
            return hmac.compare_digest(dk.hex(), stored_hash)
        return False


class TokenManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, secret_key: Optional[str] = None, algorithm: str = "HS256"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, secret_key: Optional[str] = None, algorithm: str = "HS256"):
        if self._initialized:  # pylint: disable=access-member-before-definition
            return
        self.secret_key = self._get_or_generate_secret_key(secret_key)
        self.algorithm = algorithm
        self.access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.refresh_token_expire_days = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        self.users: Dict[str, User] = {}
        self._password_hashes: Dict[str, str] = {}
        self._login_attempts: Dict[str, Dict[str, Any]] = {}
        self._login_rate_limit = int(os.environ.get("LOGIN_RATE_LIMIT", "5"))
        self._login_rate_window_seconds = int(os.environ.get("LOGIN_RATE_WINDOW_SECONDS", "60"))
        self._lock = threading.RLock()
        self._initialize_default_users()
        self._initialized = True

    def _get_or_generate_secret_key(self, provided_key: Optional[str]) -> str:
        """获取或生成密钥 - 优先从环境变量，生产环境无密钥则启动失败"""
        key = provided_key or os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET_KEY")
        if key:
            if len(key) < 32:
                raise ValueError(
                    "JWT secret key must be at least 32 bytes (256 bits). "
                    "Set SECRET_KEY environment variable with a 32+ byte key."
                )
            return key
        # 生产环境强制要求显式密钥
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env == "production":
            raise ValueError(
                "SECRET_KEY (or JWT_SECRET_KEY) environment variable must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # 开发模式：生成临时密钥并警告
        generated = secrets.token_hex(32)
        logger.warning(
            "No SECRET_KEY found in environment variables. "
            "Generated a temporary key for development. "
            "Set SECRET_KEY environment variable for production."
        )
        return generated

    def _initialize_default_users(self):
        env = os.environ.get("ENVIRONMENT", "development").lower()
        default_password = os.environ.get("DEFAULT_USER_PASSWORD")
        if not default_password:
            if env == "production":
                raise ValueError(
                    "DEFAULT_USER_PASSWORD environment variable must be set in production. "
                    "Set ENVIRONMENT=development to use the dev default."
                )
            default_password = "password"  # 仅开发模式回退
        default_users = [
            User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN),
            User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER),
            User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER),
        ]
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

        with self._lock:
            username = payload.get("username")
            user = self.users.get(username) if isinstance(username, str) else None

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

        with self._lock:
            username = payload.get("username")
            user = self.users.get(username) if isinstance(username, str) else None

            if user and user.is_active:
                return self.create_access_token(user)

        return None

    def _check_login_rate_limit(self, username: str) -> bool:
        with self._lock:
            now = datetime.now()
            attempts = self._login_attempts.get(username, {"count": 0, "first_attempt": now})
            
            elapsed = (now - attempts["first_attempt"]).total_seconds()
            if elapsed > self._login_rate_window_seconds:
                attempts = {"count": 1, "first_attempt": now}
                self._login_attempts[username] = attempts
                return True
            
            if attempts["count"] >= self._login_rate_limit:
                return False
            
            attempts["count"] += 1
            self._login_attempts[username] = attempts
            return True

    def authenticate(self, username: str, password: str) -> Optional[User]:
        with self._lock:
            if not self._check_login_rate_limit(username):
                return None

            user = self.users.get(username)
            if not user or not user.is_active:
                return None

            stored_hash = self._password_hashes.get(username, "")
            if PasswordHasher.verify_password(password, stored_hash):
                self._login_attempts.pop(username, None)
                user.last_login = datetime.now()
                return user
        return None

    def is_rate_limited(self, username: str) -> bool:
        with self._lock:
            attempts = self._login_attempts.get(username)
            if not attempts:
                return False
            now = datetime.now()
            elapsed = (now - attempts["first_attempt"]).total_seconds()
            if elapsed > self._login_rate_window_seconds:
                return False
            return attempts["count"] >= self._login_rate_limit

    def get_rate_limit_info(self, username: str) -> Dict[str, Any]:
        with self._lock:
            attempts = self._login_attempts.get(username, {"count": 0, "first_attempt": datetime.now()})
            now = datetime.now()
            elapsed = (now - attempts["first_attempt"]).total_seconds()
            remaining = max(0, self._login_rate_limit - attempts["count"])
            reset_in = max(0, self._login_rate_window_seconds - elapsed)
            return {
                "remaining": remaining,
                "reset_in": int(reset_in),
                "limit": self._login_rate_limit,
            }

    def set_password(self, username: str, password: str):
        """设置用户密码"""
        with self._lock:
            self._password_hashes[username] = PasswordHasher.hash_password(password)

    def _get_password_hash(self, username: str) -> str:
        """获取密码哈希 - 仅限内部使用"""
        with self._lock:
            return self._password_hashes.get(username, "")