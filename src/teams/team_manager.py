import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from src.security.auth import Role as UserRole

logger = logging.getLogger(__name__)


class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


@dataclass
class TeamMember:
    user_id: str
    username: str
    role: TeamRole
    joined_at: datetime = field(default_factory=datetime.now)


@dataclass
class Team:
    team_id: str
    name: str
    description: str = ""
    members: List[TeamMember] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


class TeamManager:
    def __init__(self, storage_path: str = None, use_database: bool = None):
        self.storage_path = storage_path or os.environ.get(
            "TEAM_STORAGE_PATH", "data/teams.json"
        )
        self.teams: Dict[str, Team] = {}
        self._use_database = use_database if use_database is not None else bool(
            os.environ.get("DATABASE_URL")
        )
        self._db = None
        if self._use_database:
            try:
                from src.storage.database import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"Database not available, falling back to JSON: {e}")
                self._use_database = False
        self._load_teams()

    def _load_teams(self):
        if self._use_database and self._db:
            try:
                teams_rows = self._db.select_all(self._db.teams_table)
                for row in teams_rows:
                    members_rows = self._db.select_all(
                        self._db.team_members_table,
                        self._db.team_members_table.c.team_id == row["team_id"]
                    )
                    members = [
                        TeamMember(
                            user_id=m["user_id"],
                            username=m["username"],
                            role=TeamRole(m["role"]),
                            joined_at=m.get("joined_at", datetime.now()),
                        )
                        for m in members_rows
                    ]
                    self.teams[row["team_id"]] = Team(
                        team_id=row["team_id"],
                        name=row["name"],
                        description=row.get("description", ""),
                        members=members,
                        created_at=row.get("created_at", datetime.now()),
                        updated_at=row.get("updated_at", datetime.now()),
                        metadata=row.get("metadata", {}),
                    )
                return
            except Exception as e:
                logger.warning(f"Database load failed, using JSON: {e}")

        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for team_id, team_data in data.items():
                        members = []
                        for member_data in team_data.get("members", []):
                            members.append(
                                TeamMember(
                                    user_id=member_data["user_id"],
                                    username=member_data["username"],
                                    role=TeamRole(member_data["role"]),
                                    joined_at=datetime.fromisoformat(
                                        member_data["joined_at"]
                                    ),
                                )
                            )
                        self.teams[team_id] = Team(
                            team_id=team_data["team_id"],
                            name=team_data["name"],
                            description=team_data.get("description", ""),
                            members=members,
                            created_at=datetime.fromisoformat(team_data["created_at"]),
                            updated_at=datetime.fromisoformat(team_data["updated_at"]),
                            metadata=team_data.get("metadata", {}),
                        )
            except Exception:
                self.teams = {}

    def _save_teams(self):
        if self._use_database and self._db:
            return
        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        data = {}
        for team_id, team in self.teams.items():
            data[team_id] = {
                "team_id": team.team_id,
                "name": team.name,
                "description": team.description,
                "members": [
                    {
                        "user_id": m.user_id,
                        "username": m.username,
                        "role": m.role.value,
                        "joined_at": m.joined_at.isoformat(),
                    }
                    for m in team.members
                ],
                "created_at": team.created_at.isoformat(),
                "updated_at": team.updated_at.isoformat(),
                "metadata": team.metadata,
            }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def create_team(
        self, name: str, description: str = "", owner_id: str = "", owner_username: str = ""
    ) -> Team:
        if name in [t.name for t in self.teams.values()]:
            raise ValueError(f"Team '{name}' already exists")

        team_id = f"team_{len(self.teams) + 1:04d}"
        members = []
        if owner_id:
            members.append(
                TeamMember(
                    user_id=owner_id,
                    username=owner_username,
                    role=TeamRole.OWNER,
                )
            )

        team = Team(
            team_id=team_id,
            name=name,
            description=description,
            members=members,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.teams[team_id] = team

        if self._use_database and self._db:
            self._db.insert_one(self._db.teams_table, {
                "team_id": team.team_id,
                "name": team.name,
                "description": team.description,
                "created_at": team.created_at,
                "updated_at": team.updated_at,
                "metadata": team.metadata,
            })
            for member in members:
                self._db.insert_one(self._db.team_members_table, {
                    "team_id": team.team_id,
                    "user_id": member.user_id,
                    "username": member.username,
                    "role": member.role.value,
                    "joined_at": member.joined_at,
                })
        else:
            self._save_teams()
        return team

    def get_team(self, team_id: str) -> Optional[Team]:
        return self.teams.get(team_id)

    def get_team_by_name(self, name: str) -> Optional[Team]:
        for team in self.teams.values():
            if team.name == name:
                return team
        return None

    def update_team(
        self,
        team_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team:
            return None

        if name:
            existing = self.get_team_by_name(name)
            if existing and existing.team_id != team_id:
                raise ValueError(f"Team '{name}' already exists")
            team.name = name

        if description is not None:
            team.description = description

        if metadata is not None:
            team.metadata = metadata

        team.updated_at = datetime.now()

        if self._use_database and self._db:
            self._db.update_many(
                self._db.teams_table,
                self._db.teams_table.c.team_id == team_id,
                {
                    "name": team.name,
                    "description": team.description,
                    "updated_at": team.updated_at,
                    "metadata": team.metadata,
                },
            )
        else:
            self._save_teams()
        return team

    def delete_team(self, team_id: str) -> bool:
        if team_id in self.teams:
            del self.teams[team_id]
            if self._use_database and self._db:
                self._db.delete_many(
                    self._db.team_members_table,
                    self._db.team_members_table.c.team_id == team_id,
                )
                self._db.delete_many(
                    self._db.teams_table,
                    self._db.teams_table.c.team_id == team_id,
                )
            else:
                self._save_teams()
            return True
        return False

    def add_member(
        self, team_id: str, user_id: str, username: str, role: TeamRole = TeamRole.MEMBER
    ) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team:
            return None

        for member in team.members:
            if member.user_id == user_id:
                raise ValueError(f"User '{username}' is already a member")

        team.members.append(
            TeamMember(
                user_id=user_id,
                username=username,
                role=role,
                joined_at=datetime.now(),
            )
        )
        team.updated_at = datetime.now()

        if self._use_database and self._db:
            self._db.insert_one(self._db.team_members_table, {
                "team_id": team_id,
                "user_id": user_id,
                "username": username,
                "role": role.value,
                "joined_at": datetime.now(),
            })
            self._db.update_many(
                self._db.teams_table,
                self._db.teams_table.c.team_id == team_id,
                {"updated_at": team.updated_at},
            )
        else:
            self._save_teams()
        return team

    def remove_member(self, team_id: str, user_id: str) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team:
            return None

        owner_count = sum(1 for m in team.members if m.role == TeamRole.OWNER)
        for member in team.members:
            if member.user_id == user_id:
                if member.role == TeamRole.OWNER and owner_count == 1:
                    raise ValueError("Cannot remove the only owner")
                team.members.remove(member)
                team.updated_at = datetime.now()
                if self._use_database and self._db:
                    self._db.delete_many(
                        self._db.team_members_table,
                        (self._db.team_members_table.c.team_id == team_id) &
                        (self._db.team_members_table.c.user_id == user_id),
                    )
                    self._db.update_many(
                        self._db.teams_table,
                        self._db.teams_table.c.team_id == team_id,
                        {"updated_at": team.updated_at},
                    )
                else:
                    self._save_teams()
                return team

        return None

    def update_member_role(
        self, team_id: str, user_id: str, new_role: TeamRole
    ) -> Optional[Team]:
        team = self.teams.get(team_id)
        if not team:
            return None

        for member in team.members:
            if member.user_id == user_id:
                owner_count = sum(1 for m in team.members if m.role == TeamRole.OWNER)
                if member.role == TeamRole.OWNER and owner_count == 1:
                    raise ValueError("Cannot change the role of the only owner")
                member.role = new_role
                team.updated_at = datetime.now()
                if self._use_database and self._db:
                    self._db.update_many(
                        self._db.team_members_table,
                        (self._db.team_members_table.c.team_id == team_id) &
                        (self._db.team_members_table.c.user_id == user_id),
                        {"role": new_role.value},
                    )
                    self._db.update_many(
                        self._db.teams_table,
                        self._db.teams_table.c.team_id == team_id,
                        {"updated_at": team.updated_at},
                    )
                else:
                    self._save_teams()
                return team

        return None

    def list_teams(self) -> List[Team]:
        return sorted(self.teams.values(), key=lambda t: t.created_at, reverse=True)

    def get_user_teams(self, user_id: str) -> List[Team]:
        teams = []
        for team in self.teams.values():
            for member in team.members:
                if member.user_id == user_id:
                    teams.append(team)
                    break
        return sorted(teams, key=lambda t: t.created_at, reverse=True)

    def get_team_members(self, team_id: str) -> List[TeamMember]:
        team = self.teams.get(team_id)
        if not team:
            return []
        return team.members

    def count_teams(self) -> Dict[str, int]:
        return {
            "total": len(self.teams),
            "total_members": sum(len(t.members) for t in self.teams.values()),
        }