import os
import threading
from pathlib import Path
from typing import Optional


class SecurePathValidator:
    """路径安全校验器 - 基于项目根前缀匹配。

    修复 BUG-006:
    - 旧实现先 resolve() 再查 ..,该检查永不触发(死代码)
    - 旧实现用 parts[i] in ALLOWED_DIRS 子串匹配,/etc/tests/passwd 等越权路径放行
    - 新实现:
      1. .. 检查移到 resolve() 之前(基于原始 Path.parts)
      2. 用 path.relative_to(project_root) 做前缀匹配
      3. 显式 project_root 参数,优先级:参数 > PROJECT_ROOT 环境变量 > os.getcwd()
    """

    ALLOWED_DIRS = {"tests", "reports", "data", "output", "src"}

    def __init__(self, project_root: Optional[str] = None):
        self._lock = threading.Lock()
        # 项目根:优先显式传入 > 环境变量 > 当前工作目录
        root = project_root or os.environ.get("PROJECT_ROOT") or os.getcwd()
        self._project_root = Path(root).resolve()

    def validate_path(self, target_path: str) -> tuple[bool, str]:
        with self._lock:
            try:
                if not isinstance(target_path, str):
                    return False, "Path must be a string"

                if "\x00" in target_path:
                    return False, "NULL byte injection detected"

                if len(target_path) > 255:
                    return False, "Path exceeds maximum length"

                # 防御性检查:原始路径含 .. 直接拒绝(resolve 前查才有效)
                if ".." in Path(target_path).parts:
                    return False, "Path traversal detected"

                path = Path(target_path).resolve()

                if not path.is_absolute():
                    return False, "Path must be absolute"

                # 前缀匹配:路径必须在项目根下
                try:
                    path.relative_to(self._project_root)
                except ValueError:
                    return False, f"Path escapes project root: {path}"

                # 必须落在 ALLOWED_DIRS 的某个一级子目录
                relative_parts = path.relative_to(self._project_root).parts
                if not relative_parts:
                    return False, "Path is project root itself"
                if relative_parts[0] not in self.ALLOWED_DIRS:
                    return False, f"Path not in allowed directory: {relative_parts[0]}"

                return True, f"Path validated: {path}"

            except Exception as e:
                return False, f"Path validation error: {str(e)}"

    def is_sandboxed(self, target_path: str) -> bool:
        valid, _ = self.validate_path(target_path)
        return valid

    def sanitize_path(self, target_path: str, base_dir: Optional[str] = None) -> str:
        with self._lock:
            if base_dir:
                base_path = Path(base_dir).resolve()
            else:
                base_path = Path.cwd().resolve()

            target = Path(target_path)

            if target.is_absolute():
                resolved = target.resolve()
            else:
                resolved = (base_path / target).resolve()

            if not str(resolved).startswith(str(base_path)):
                raise ValueError(f"Path escapes sandbox: {target_path}")

            return str(resolved)
