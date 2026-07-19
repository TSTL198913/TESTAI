# tests/governance/test_git_manager.py
"""
GitTransactionManager 单元测试 - 验证真实 git 事务行为

使用临时 git 仓库，不 Mock，验证真实事务创建、提交、回滚行为。
这是 P1 阶段的重要补充：确保 git 事务在隔离环境中正常工作，
而非在生产环境中因未提交更改阻塞。
"""
import os
import subprocess
import tempfile

import pytest

from src.governance.git_manager import GitTransactionManager


class TestGitTransactionManager:
    """验证 GitTransactionManager 的真实 git 事务行为"""

    @pytest.fixture
    def temp_git_repo(self):
        """创建临时 git 仓库，确保隔离环境"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 初始化 git 仓库
            subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@testai.local"], cwd=tmp_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "TestAI"], cwd=tmp_dir, check=True, capture_output=True)
            
            # 创建初始文件
            with open(os.path.join(tmp_dir, "initial.py"), "w") as f:
                f.write("def hello():\n    return 'world'\n")
            
            subprocess.run(["git", "add", "."], cwd=tmp_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_dir, check=True, capture_output=True)
            
            yield tmp_dir

    def test_base_branch_detection(self, temp_git_repo):
        """验证 base_branch 能正确检测"""
        manager = GitTransactionManager(temp_git_repo)
        assert manager.base_branch in ["main", "master"]

    def test_start_transaction_creates_branch(self, temp_git_repo):
        """验证 start_transaction 创建治理分支"""
        manager = GitTransactionManager(temp_git_repo)
        tx_id = "test_tx_001"
        
        manager.start_transaction(tx_id)
        
        # 验证分支已创建
        result = subprocess.run(
            ["git", "branch"], cwd=temp_git_repo, capture_output=True, text=True
        )
        assert f"governance_{tx_id}" in result.stdout

    def test_start_transaction_cleanup_existing_branch(self, temp_git_repo):
        """验证 start_transaction 清理已存在的同名分支"""
        manager = GitTransactionManager(temp_git_repo)
        tx_id = "test_tx_002"
        
        # 手动创建分支
        subprocess.run(
            ["git", "checkout", "-b", f"governance_{tx_id}"],
            cwd=temp_git_repo, check=True, capture_output=True
        )
        # 使用检测到的 base_branch
        subprocess.run(
            ["git", "checkout", manager.base_branch], 
            cwd=temp_git_repo, check=True, capture_output=True
        )
        
        # 再次启动事务，应清理旧分支
        manager.start_transaction(tx_id)
        
        # 验证新分支已创建
        result = subprocess.run(
            ["git", "branch"], cwd=temp_git_repo, capture_output=True, text=True
        )
        assert f"governance_{tx_id}" in result.stdout

    def test_commit_saves_changes(self, temp_git_repo):
        """验证 commit 保存更改"""
        manager = GitTransactionManager(temp_git_repo)
        tx_id = "test_tx_003"
        
        manager.start_transaction(tx_id)
        
        # 在事务分支上创建文件
        with open(os.path.join(temp_git_repo, "new_file.txt"), "w") as f:
            f.write("test content")
        
        manager.commit("Add new file")
        
        # 验证文件已提交
        result = subprocess.run(
            ["git", "show", "HEAD:new_file.txt"],
            cwd=temp_git_repo, capture_output=True, text=True
        )
        assert result.stdout.strip() == "test content"

    def test_rollback_restores_base_branch(self, temp_git_repo):
        """验证 rollback 恢复到 base 分支"""
        manager = GitTransactionManager(temp_git_repo)
        tx_id = "test_tx_004"
        
        manager.start_transaction(tx_id)
        
        # 在事务分支上创建文件
        with open(os.path.join(temp_git_repo, "rollback_test.txt"), "w") as f:
            f.write("should be deleted")
        
        manager.commit("Add rollback test")
        
        # 回滚
        manager.rollback(tx_id)
        
        # 验证回到 base 分支
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_git_repo, capture_output=True, text=True
        )
        assert result.stdout.strip() == manager.base_branch
        
        # 验证治理分支已删除
        result = subprocess.run(
            ["git", "branch"], cwd=temp_git_repo, capture_output=True, text=True
        )
        assert f"governance_{tx_id}" not in result.stdout

    def test_transaction_complete_flow(self, temp_git_repo):
        """验证完整事务流程：start → commit → rollback"""
        manager = GitTransactionManager(temp_git_repo)
        tx_id = "test_tx_005"
        
        # 启动事务
        manager.start_transaction(tx_id)
        
        # 修改文件
        target_file = os.path.join(temp_git_repo, "initial.py")
        with open(target_file, "r") as f:
            content = f.read()
        assert "return 'world'" in content
        
        with open(target_file, "w") as f:
            f.write("def hello():\n    return 'modified'\n")
        
        # 提交
        manager.commit("Modify hello function")
        
        # 验证修改已提交
        result = subprocess.run(
            ["git", "show", "HEAD:initial.py"],
            cwd=temp_git_repo, capture_output=True, text=True
        )
        assert "return 'modified'" in result.stdout
        
        # 回滚
        manager.rollback(tx_id)
        
        # 验证恢复原始内容
        with open(target_file, "r") as f:
            content = f.read()
        assert "return 'world'" in content
        assert "return 'modified'" not in content