import pytest
from unittest.mock import patch, MagicMock
from src.teams.team_manager import TeamManager, TeamRole


class TestTeamManagerDbConsistency:
    def test_create_team_db_failure_rolls_back_memory(self, tmp_path):
        storage_path = tmp_path / "test_team_consistency.json"
        team_manager = TeamManager(storage_path=str(storage_path), use_database=False)
        
        with patch('src.storage.database.get_db_manager') as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            mock_db.insert_one.side_effect = RuntimeError("Database connection failed")
            
            team_manager._use_database = True
            team_manager._db = mock_db

            with pytest.raises(RuntimeError):
                team_manager.create_team(name="Test Team")

            assert "team_" not in [t.team_id for t in team_manager.teams.values()], \
                "Team should not exist in memory if database insertion failed"

    def test_add_member_db_failure_rolls_back_memory(self, tmp_path):
        storage_path = tmp_path / "test_member_consistency.json"
        team_manager = TeamManager(storage_path=str(storage_path), use_database=False)
        team = team_manager.create_team(name="Test Team")

        with patch('src.storage.database.get_db_manager') as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            mock_db.insert_one.side_effect = RuntimeError("Database connection failed")
            
            team_manager._use_database = True
            team_manager._db = mock_db

            with pytest.raises(RuntimeError):
                team_manager.add_member(
                    team_id=team.team_id,
                    user_id="user_0001",
                    username="testuser",
                    role=TeamRole.MEMBER,
                )

            assert len(team_manager.get_team(team.team_id).members) == 0, \
                "Member should not be added if database insertion failed"