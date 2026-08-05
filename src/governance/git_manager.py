# src/governance/git_manager.py
import logging
import re
import subprocess  # nosec B404
import shutil
import threading
from typing import Optional

GIT_PATH = shutil.which("git") or "git"


class GitTransactionManager:
    _branch_name_pattern = re.compile(r"[^a-zA-Z0-9_-]")

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.logger = logging.getLogger("GitTransaction")
        self.base_branch = self._detect_base_branch()
        self._lock = threading.Lock()

    def _sanitize_branch_name(self, tx_id: str) -> str:
        sanitized = self._branch_name_pattern.sub("_", tx_id)
        max_length = 64 - len("governance_")
        return f"governance_{sanitized[:max_length]}"

    def _detect_base_branch(self) -> str:
        for branch in ["main", "master"]:
            try:
                result = subprocess.run(
                    [GIT_PATH, "show-ref", "--verify", f"refs/heads/{branch}"],
                    cwd=self.repo_path,
                    capture_output=True,
                )  # nosec B603
                if result.returncode == 0:
                    return branch
            except Exception as e:
                self.logger.debug(f"Failed to check branch {branch}: {e}")
                continue
        return "master"

    def _run(self, cmd: list[str]):
        """封装带有检查的执行器"""
        try:
            if cmd[0] == "git":
                cmd[0] = GIT_PATH
            subprocess.run(
                cmd, cwd=self.repo_path, check=True, capture_output=True, text=True
            )  # nosec B603
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Git Command Failed: {' '.join(cmd)} | Error: {e.stderr}"
            )
            raise e

    def start_transaction(self, tx_id: str):
        with self._lock:
            branch_name = self._sanitize_branch_name(tx_id)
            self._run(["git", "checkout", self.base_branch])
            try:
                result = subprocess.run(
                    [GIT_PATH, "show-ref", "--verify", f"refs/heads/{branch_name}"],
                    cwd=self.repo_path,
                    capture_output=True,
                )  # nosec B603
                if result.returncode == 0:
                    self._run(["git", "branch", "-D", branch_name])
            except Exception as e:
                self.logger.warning(
                    f"Failed to check/clean existing branch {branch_name}: {e}"
                )
            self._run(["git", "checkout", "-b", branch_name])

    def commit(self, message: str):
        with self._lock:
            self._run(["git", "add", "."])
            self._run(["git", "commit", "-m", message])

    def rollback(self, tx_id: str):
        """回滚并清理现场"""
        with self._lock:
            # 关键修复: rollback 必须用 _sanitize_branch_name(tx_id) 与 start_transaction 一致,
            # 否则 tx_id 含特殊字符时, start 创建的是 governance_tx_a_b_c,
            # rollback 删除的是 governance_tx_a/b:c → branch -D 失败 → 假回滚。
            branch_name = self._sanitize_branch_name(tx_id)
            try:
                self._run(["git", "checkout", self.base_branch])
                try:
                    self._run(["git", "branch", "-D", branch_name])
                except Exception as e:
                    self.logger.debug(f"Branch {branch_name} does not exist or cannot be deleted: {e}")
                self.logger.info(f"Transaction {tx_id} rolled back successfully.")
            except Exception as e:
                self.logger.critical(f"FATAL: Rollback failed for {tx_id}: {e}")
                raise
