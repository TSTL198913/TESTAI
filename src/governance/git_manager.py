# src/governance/git_manager.py
import logging
import subprocess
from typing import Optional


class GitTransactionManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.logger = logging.getLogger("GitTransaction")
        self.base_branch = self._detect_base_branch()

    def _detect_base_branch(self) -> str:
        for branch in ["main", "master"]:
            try:
                result = subprocess.run(
                    ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
                    cwd=self.repo_path,
                    capture_output=True,
                )
                if result.returncode == 0:
                    return branch
            except Exception:
                continue
        return "master"

    def _run(self, cmd: list[str]):
        """封装带有检查的执行器"""
        try:
            subprocess.run(
                cmd, cwd=self.repo_path, check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Git Command Failed: {' '.join(cmd)} | Error: {e.stderr}"
            )
            raise e

    def start_transaction(self, tx_id: str):
        branch_name = f"governance_{tx_id}"
        self._run(["git", "checkout", self.base_branch])
        try:
            result = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"],
                cwd=self.repo_path,
                capture_output=True,
            )
            if result.returncode == 0:
                self._run(["git", "branch", "-D", branch_name])
        except Exception as e:
            self.logger.warning(
                f"Failed to check/clean existing branch {branch_name}: {e}"
            )
        self._run(["git", "checkout", "-b", branch_name])

    def commit(self, message: str):
        self._run(["git", "add", "."])
        self._run(["git", "commit", "-m", message])

    def rollback(self, tx_id: str):
        """回滚并清理现场"""
        try:
            self._run(["git", "checkout", self.base_branch])
            try:
                self._run(["git", "branch", "-D", f"governance_{tx_id}"])
            except Exception:
                pass
            self.logger.info(f"Transaction {tx_id} rolled back successfully.")
        except Exception as e:
            self.logger.critical(f"FATAL: Rollback failed for {tx_id}: {e}")
            raise
