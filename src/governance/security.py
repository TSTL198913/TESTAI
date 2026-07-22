import os
import threading
from pathlib import Path
from typing import Optional


class SecurePathValidator:
    ALLOWED_DIRS = {"tests", "reports", "data", "output", "src"}

    def __init__(self):
        self._lock = threading.Lock()

    def validate_path(self, target_path: str) -> tuple[bool, str]:
        with self._lock:
            try:
                if not isinstance(target_path, str):
                    return False, "Path must be a string"

                if "\x00" in target_path:
                    return False, "NULL byte injection detected"

                if len(target_path) > 255:
                    return False, "Path exceeds maximum length"

                path = Path(target_path).resolve()

                if not path.is_absolute():
                    return False, "Path must be absolute"

                if ".." in str(path):
                    return False, "Path traversal detected"

                parts = path.parts

                for i in range(len(parts)):
                    if parts[i] in self.ALLOWED_DIRS:
                        return True, f"Path validated: {path}"

                return False, f"Path not in allowed directory: {path}"

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
