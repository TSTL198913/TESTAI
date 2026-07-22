import logging
import os
import shutil
import stat
from pathlib import Path
from typing import List, Optional

import libcst as cst

from src.governance.registry import GovernanceRegistry, PatchType
from src.governance.security import SecurePathValidator


class SecurityVisitor(cst.CSTVisitor):
    def __init__(self):
        self.forbidden_functions = {"eval", "exec", "compile"}
        self.forbidden_attrs = {"subprocess", "os"}
        self.is_unsafe = False
        self.unsafe_reason = ""

    def visit_Call(self, node: cst.Call):
        if (
            isinstance(node.func, cst.Name)
            and node.func.value in self.forbidden_functions
        ):
            self.is_unsafe = True
            self.unsafe_reason = f"Forbidden function call: {node.func.value}"

        elif isinstance(node.func, cst.Attribute):
            if (
                isinstance(node.func.value, cst.Name)
                and node.func.value.value in self.forbidden_attrs
            ):
                self.is_unsafe = True
                self.unsafe_reason = f"Forbidden attribute access: {node.func.value.value}.{node.func.attr.value}"


class GovernanceExecutor:
    def __init__(self):
        self.logger = logging.getLogger("GovernanceExecutor")
        self._path_validator = SecurePathValidator()

    def validate_file_path(self, file_path: str) -> bool:
        valid, reason = self._path_validator.validate_path(file_path)
        if not valid:
            self.logger.critical(f"PATH VALIDATION FAILED: {reason}")
        return valid

    def is_safe_patch(self, code: str) -> bool:
        try:
            tree = cst.parse_module(code)
            visitor = SecurityVisitor()
            tree.visit(visitor)

            if visitor.is_unsafe:
                self.logger.critical(f"SECURITY ALERT: {visitor.unsafe_reason}")
                return False
            return True
        except Exception as e:
            self.logger.error(f"Security Gate failed to parse code: {e}")
            return False

    async def apply_patch(
        self,
        file_path: str,
        patch_type: PatchType,
        target_function: str,
        suggested_code: str,
        required_imports: Optional[List[str]] = None,
        target_class: Optional[str] = None,
    ) -> bool:

        if not self.is_safe_patch(suggested_code):
            return False

        if not self.validate_file_path(file_path):
            self.logger.critical(f"Patch rejected: unsafe file path '{file_path}'")
            return False

        full_path = Path(file_path)
        backup_path = full_path.with_suffix(full_path.suffix + ".bak")

        if not full_path.exists():
            self.logger.error(f"File not found: {full_path}")
            return False

        if not self._has_write_permission(full_path):
            self.logger.warning(
                f"No write permission for: {full_path}. Attempting to grant..."
            )
            if not self._grant_write_permission(full_path):
                self.logger.error(f"Failed to obtain write permission for: {full_path}")
                return False

        try:
            shutil.copy2(full_path, backup_path)
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return False

        try:
            self._write_patch(
                full_path,
                patch_type,
                target_function,
                suggested_code,
                required_imports or [],
                target_class=target_class,
            )

            if backup_path.exists():
                backup_path.unlink()
            return True

        except PermissionError as e:
            self.logger.critical(
                f"Patch failed due to permission error: {e}. Restoring backup..."
            )
            if backup_path.exists():
                shutil.move(backup_path, full_path)
            return False
        except Exception as e:
            self.logger.critical(f"Patch failed: {e}. Restoring backup...")
            if backup_path.exists():
                shutil.move(backup_path, full_path)
            return False

    def _has_write_permission(self, path: Path) -> bool:
        try:
            if os.access(path, os.W_OK):
                return True
            with open(path, "a"):
                pass
            return True
        except (PermissionError, OSError):
            return False

    def _grant_write_permission(self, path: Path) -> bool:
        try:
            current_stat = path.stat()
            path.chmod(current_stat.st_mode | stat.S_IWUSR | stat.S_IWGRP)
            return True
        except Exception as e:
            self.logger.error(f"Failed to change permissions via chmod: {e}")

        try:
            import subprocess
            import shutil

            icacls_path = shutil.which("icacls") or "icacls"
            result = subprocess.run(
                [icacls_path, str(path), "/grant", "Users:F"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.logger.info(f"Permissions granted via icacls: {str(path)}")
                return True
            else:
                self.logger.error(f"icacls failed: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to grant permissions via icacls: {e}")
            return False

    def _write_patch(
        self,
        file_path: Path,
        patch_type: PatchType,
        target_function: str,
        suggested_code: str,
        required_imports: List[str],
        target_class: Optional[str] = None,
    ):
        content = file_path.read_text(encoding="utf-8")
        tree = cst.parse_module(content)

        transformer = GovernanceRegistry.create_transformer(
            patch_type,
            target_function=target_function,
            new_body=suggested_code,
            required_imports=required_imports,
            target_class=target_class,
        )

        new_tree = tree.visit(transformer)

        if not getattr(transformer, "patched", False):
            raise RuntimeError(
                f"Target '{target_class or ''}.{target_function}' not found."
            )

        temp_file = file_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as tf:
            tf.write(new_tree.code)

        try:
            cst.parse_module(new_tree.code)
        except Exception as e:
            temp_file.unlink()
            raise RuntimeError(f"生成的补丁存在语法错误，拒绝提交: {e}")

        try:
            os.replace(temp_file, file_path)
        except OSError as e:
            try:
                shutil.copy2(temp_file, file_path)
                temp_file.unlink()
            except Exception as copy_e:
                temp_file.unlink()
                raise RuntimeError(f"Patch apply failed: {copy_e}") from e
