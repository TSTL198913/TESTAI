"""BUG-066: TeamManager 数据一致性问题 - 删除用户时未清理团队成员记录。

源码位置: src/teams/team_manager.py:328-355

根因:
1. UserManager.delete_user() 删除用户时，没有通知 TeamManager
2. TeamManager.remove_member() 需要手动调用，否则已删除用户仍留在团队成员列表中
3. 这导致团队成员引用已不存在的用户，数据不一致

正确行为:
- 删除用户时应自动清理其在所有团队中的成员记录
- 或在查询团队成员时验证用户是否存在
"""
import pytest
import tempfile
import os

from src.users.user_manager import UserManager, UserStatus
from src.teams.team_manager import TeamManager, TeamRole
from src.security.auth import Role


class TestTeamManagerDataConsistency:
    """TeamManager数据一致性测试"""

    def setup_method(self):
        UserManager._instance = None
        TeamManager._instance = None

    def teardown_method(self):
        UserManager._instance = None
        TeamManager._instance = None

    def test_deleted_user_still_in_team_members(self):
        """删除用户后，用户仍留在团队成员列表中（数据不一致）"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            user_storage = os.path.join(tmp_dir, "users.json")
            team_storage = os.path.join(tmp_dir, "teams.json")
            
            user_manager = UserManager(storage_path=user_storage)
            team_manager = TeamManager(storage_path=team_storage)
            
            user = user_manager.create_user(
                username="test_user",
                email="test@test.com",
                role=Role.TESTER,
            )
            
            team = team_manager.create_team(name="Test Team")
            team_manager.add_member(team.team_id, user.user_id, user.username, TeamRole.MEMBER)
            
            assert len(team.members) == 1
            assert team.members[0].user_id == user.user_id
            
            user_manager.delete_user(user.user_id)
            
            assert user_manager.get_user(user.user_id) is None
            
            team = team_manager.get_team(team.team_id)
            assert team is not None
            
            assert len(team.members) == 1, (
                f"Expected deleted user to still be in team (demonstrating bug), "
                f"but team has {len(team.members)} members"
            )
            assert team.members[0].user_id == user.user_id, (
                "Expected deleted user's ID to still be in team members"
            )

    def test_get_user_teams_returns_teams_for_deleted_user(self):
        """已删除用户仍能获取其团队列表"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            user_storage = os.path.join(tmp_dir, "users.json")
            team_storage = os.path.join(tmp_dir, "teams.json")
            
            user_manager = UserManager(storage_path=user_storage)
            team_manager = TeamManager(storage_path=team_storage)
            
            user = user_manager.create_user(
                username="test_user2",
                email="test2@test.com",
                role=Role.TESTER,
            )
            
            team = team_manager.create_team(name="Test Team 2")
            team_manager.add_member(team.team_id, user.user_id, user.username, TeamRole.MEMBER)
            
            user_manager.delete_user(user.user_id)
            
            user_teams = team_manager.get_user_teams(user.user_id)
            
            assert len(user_teams) == 1, (
                f"Expected deleted user to still have team (demonstrating bug), "
                f"but got {len(user_teams)} teams"
            )

    def test_team_member_validation_missing(self):
        """团队成员验证缺失 - 添加不存在的用户到团队"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            team_storage = os.path.join(tmp_dir, "teams.json")
            
            team_manager = TeamManager(storage_path=team_storage)
            
            team = team_manager.create_team(name="Test Team 3")
            
            result = team_manager.add_member(
                team.team_id,
                user_id="non_existent_user_id",
                username="non_existent_user",
                role=TeamRole.MEMBER,
            )
            
            assert result is not None, (
                "Expected to be able to add non-existent user (demonstrating bug)"
            )
            assert len(team.members) == 1