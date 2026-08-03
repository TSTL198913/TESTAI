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
            try:
                self._run(["git", "checkout", self.base_branch])
                # P2-2 修复: 回滚分支名必须与 start_transaction 一致（都用 _sanitize_branch_name）。
                # 原实现用 f"governance_{tx_id}"（原始 tx_id），与 start 的 sanitized 分支名不一致，
                # 含特殊字符的 tx_id 会因分支名不匹配而删除失败，事务未真正回滚。
                branch_name = self._sanitize_branch_name(tx_id)
                try:
                    self._run(["git", "branch", "-D", branch_name])
                except Exception as e:
                    self.logger.debug(f"Branch {branch_name} does not exist or cannot be deleted: {e}")
                self.logger.info(f"Transaction {tx_id} rolled back successfully.")
            except Exception as e:
                self.logger.critical(f"FATAL: Rollback failed for {tx_id}: {e}")
                raise
