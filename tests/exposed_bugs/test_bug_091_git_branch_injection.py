"""BUG-091: Git分支名注入风险 - tx_id直接用于分支名，可能包含特殊字符导致命令注入或异常。

源码位置: src/governance/git_manager.py:55-71

根因:
1. tx_id直接拼接到分支名 `governance_{tx_id}`
2. 未过滤特殊字符（如空格、斜杠、引号等）
3. 超长tx_id可能导致分支名超过Git限制

修复方案:
- 添加 `_sanitize_branch_name` 方法
- 使用正则过滤非法字符，替换为下划线
- 限制分支名长度为64字符
"""
import pytest
import re
from unittest.mock import patch, MagicMock

from src.governance.git_manager import GitTransactionManager


class TestGitBranchInjection:
    """Git分支名注入风险测试"""

    def test_sanitize_branch_name_removes_special_characters(self):
        """清理特殊字符"""
        manager = GitTransactionManager("/fake/repo")
        
        tx_id = "tx;rm -rf /;echo 'hacked'"
        branch_name = manager._sanitize_branch_name(tx_id)
        
        assert ";" not in branch_name
        assert "/" not in branch_name
        assert "'" not in branch_name
        assert branch_name == "governance_tx_rm_-rf___echo__hacked_"

    def test_sanitize_branch_name_limits_length(self):
        """限制分支名长度"""
        manager = GitTransactionManager("/fake/repo")
        
        long_tx_id = "a" * 100
        branch_name = manager._sanitize_branch_name(long_tx_id)
        
        assert len(branch_name) <= 64
        assert branch_name.startswith("governance_")

    def test_sanitize_branch_name_with_special_chars(self):
        """处理各种特殊字符"""
        manager = GitTransactionManager("/fake/repo")
        
        test_cases = [
            ("tx/with/slashes", "governance_tx_with_slashes"),
            ("tx with spaces", "governance_tx_with_spaces"),
            ("tx@#$%^&*()", "governance_tx_________"),
            ("tx'\"`", "governance_tx___"),
            ("tx<>[]{}", "governance_tx______"),
        ]
        
        for tx_id, expected in test_cases:
            branch_name = manager._sanitize_branch_name(tx_id)
            assert branch_name == expected

    def test_sanitize_branch_name_valid_chars_preserved(self):
        """保留有效字符"""
        manager = GitTransactionManager("/fake/repo")
        
        tx_id = "tx_123-valid_chars"
        branch_name = manager._sanitize_branch_name(tx_id)
        
        assert branch_name == "governance_tx_123-valid_chars"

    def test_start_transaction_uses_sanitized_name(self):
        """start_transaction使用清理后的分支名"""
        with patch("src.governance.git_manager.GitTransactionManager._run") as mock_run:
            with patch("src.governance.git_manager.subprocess.run") as mock_subprocess:
                mock_subprocess.returncode = 1
                
                manager = GitTransactionManager("/fake/repo")
                manager.start_transaction("tx;rm -rf /")
                
                calls = [str(call) for call in mock_run.call_args_list]
                branch_calls = [c for c in calls if "checkout" in c]
                
                assert len(branch_calls) >= 1
                assert "governance_tx_rm_-rf_" in str(mock_run.call_args_list)