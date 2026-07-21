import pytest
import os
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.users.user_manager import UserManager, UserProfile, UserStatus
from src.security.auth import Role
from src.teams.team_manager import TeamManager, TeamMember, TeamRole
from src.ops.system_ops import SystemOperations, AuditAction, AuditResource, SystemConfig
from src.monitoring.alert_manager import AlertManager, Alert, AlertLevel, AlertType, AlertStatus, AlertRule
from src.monitoring.notification import NotificationManager, NotificationChannel, EmailNotifier, DingTalkNotifier, FeishuNotifier


class TestUserManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "users.json")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_user_success(self):
        manager = UserManager(storage_path=self.storage_path)
        user = manager.create_user(
            username="testuser",
            email="test@example.com",
            role=Role.TESTER,
            full_name="Test User",
            department="Test Dept",
        )
        
        assert user.user_id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == Role.TESTER
        assert user.status == UserStatus.ACTIVE
        assert user.full_name == "Test User"
        assert user.department == "Test Dept"

    def test_create_user_duplicate_username(self):
        manager = UserManager(storage_path=self.storage_path)
        manager.create_user(username="duplicate", email="a@example.com", role=Role.TESTER)
        
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username="duplicate", email="b@example.com", role=Role.TESTER)

    def test_create_user_duplicate_email(self):
        manager = UserManager(storage_path=self.storage_path)
        manager.create_user(username="user1", email="duplicate@example.com", role=Role.TESTER)
        
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username="user2", email="duplicate@example.com", role=Role.TESTER)

    def test_get_user_by_username(self):
        manager = UserManager(storage_path=self.storage_path)
        manager.create_user(username="lookupuser", email="lookup@example.com", role=Role.VIEWER)
        
        user = manager.get_user_by_username("lookupuser")
        assert user is not None
        assert user.email == "lookup@example.com"

    def test_update_user_status(self):
        manager = UserManager(storage_path=self.storage_path)
        user = manager.create_user(username="statususer", email="status@example.com", role=Role.TESTER)
        
        updated = manager.suspend_user(user.user_id)
        assert updated.status == UserStatus.SUSPENDED
        
        updated = manager.activate_user(user.user_id)
        assert updated.status == UserStatus.ACTIVE

    def test_delete_user(self):
        manager = UserManager(storage_path=self.storage_path)
        user = manager.create_user(username="deleteuser", email="delete@example.com", role=Role.TESTER)
        
        assert manager.delete_user(user.user_id) is True
        assert manager.get_user(user.user_id) is None

    def test_list_users_filter_by_role(self):
        manager = UserManager(storage_path=self.storage_path)
        manager.create_user(username="admin1", email="admin1@example.com", role=Role.ADMIN)
        manager.create_user(username="tester1", email="tester1@example.com", role=Role.TESTER)
        
        admins = manager.list_users(role=Role.ADMIN)
        assert len(admins) >= 1
        assert all(u.role == Role.ADMIN for u in admins)

    def test_count_users(self):
        manager = UserManager(storage_path=self.storage_path)
        counts = manager.count_users()
        
        assert "total" in counts
        assert "role_admin" in counts
        assert "status_active" in counts
        assert counts["total"] >= 0

    def test_update_last_login(self):
        manager = UserManager(storage_path=self.storage_path)
        user = manager.create_user(username="loginuser", email="login@example.com", role=Role.TESTER)
        
        assert user.last_login_at is None
        manager.update_last_login(user.user_id)
        
        updated = manager.get_user(user.user_id)
        assert updated.last_login_at is not None


class TestTeamManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "teams.json")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_team(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Test Team", description="Test Description")
        
        assert team.team_id is not None
        assert team.name == "Test Team"
        assert team.description == "Test Description"

    def test_create_team_duplicate_name(self):
        manager = TeamManager(storage_path=self.storage_path)
        manager.create_team(name="Duplicate Team")
        
        with pytest.raises(ValueError, match="already exists"):
            manager.create_team(name="Duplicate Team")

    def test_add_member(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Member Team")
        
        team = manager.add_member(team.team_id, "user1", "username1", TeamRole.MEMBER)
        assert len(team.members) == 1
        assert team.members[0].user_id == "user1"
        assert team.members[0].role == TeamRole.MEMBER

    def test_add_member_duplicate(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Duplicate Member Team")
        manager.add_member(team.team_id, "user1", "username1", TeamRole.MEMBER)
        
        with pytest.raises(ValueError, match="already a member"):
            manager.add_member(team.team_id, "user1", "username1", TeamRole.MEMBER)

    def test_remove_member(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Remove Team")
        manager.add_member(team.team_id, "user1", "username1", TeamRole.MEMBER)
        
        team = manager.remove_member(team.team_id, "user1")
        assert len(team.members) == 0

    def test_remove_only_owner(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Owner Team", owner_id="owner1", owner_username="owner")
        
        with pytest.raises(ValueError, match="only owner"):
            manager.remove_member(team.team_id, "owner1")

    def test_update_member_role(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Role Team", owner_id="owner1", owner_username="owner")
        manager.add_member(team.team_id, "user1", "username1", TeamRole.MEMBER)
        
        team = manager.update_member_role(team.team_id, "user1", TeamRole.ADMIN)
        assert team.members[1].role == TeamRole.ADMIN

    def test_get_user_teams(self):
        manager = TeamManager(storage_path=self.storage_path)
        team1 = manager.create_team(name="User Team 1")
        team2 = manager.create_team(name="User Team 2")
        manager.add_member(team1.team_id, "user1", "username1", TeamRole.MEMBER)
        manager.add_member(team2.team_id, "user1", "username1", TeamRole.MEMBER)
        
        user_teams = manager.get_user_teams("user1")
        assert len(user_teams) == 2

    def test_delete_team(self):
        manager = TeamManager(storage_path=self.storage_path)
        team = manager.create_team(name="Delete Team")
        
        assert manager.delete_team(team.team_id) is True
        assert manager.get_team(team.team_id) is None

    def test_count_teams(self):
        manager = TeamManager(storage_path=self.storage_path)
        counts = manager.count_teams()
        
        assert "total" in counts
        assert "total_members" in counts


class TestSystemOperations:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log_path = os.path.join(self.temp_dir, "audit.json")
        self.config_path = os.path.join(self.temp_dir, "config.json")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_audit(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        log = ops.log_audit(
            user_id="user1",
            username="testuser",
            action=AuditAction.CREATE,
            resource=AuditResource.USER,
            resource_id="user_0001",
            details={"name": "test"},
        )
        
        assert log.log_id is not None
        assert log.action == AuditAction.CREATE
        assert log.resource == AuditResource.USER

    def test_get_audit_logs_filtered(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        ops.log_audit("user1", "testuser", AuditAction.CREATE, AuditResource.USER)
        
        result = ops.get_audit_logs(action=AuditAction.CREATE)
        assert result["total"] >= 1

    def test_get_config(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        config = ops.get_config("system.name")
        assert config is not None
        assert config.key == "system.name"

    def test_get_config_value(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        value = ops.get_config_value("system.name")
        assert value == "TestAI"

    def test_set_config(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        config = ops.set_config("test.key", "test.value", "Test Config")
        assert config.value == "test.value"
        
        retrieved = ops.get_config("test.key")
        assert retrieved.value == "test.value"

    def test_set_config_not_editable(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        with pytest.raises(ValueError, match="not editable"):
            ops.set_config("system.version", "2.0.0")

    def test_list_configs_by_category(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        configs = ops.list_configs(category="system")
        assert len(configs) >= 1

    def test_get_system_status(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        status = ops.get_system_status()
        assert "status" in status
        assert "version" in status
        assert status["status"] == "healthy"

    def test_count_audit_logs(self):
        ops = SystemOperations(
            audit_log_path=self.audit_log_path,
            config_path=self.config_path,
        )
        
        counts = ops.count_audit_logs()
        assert "total" in counts
        assert "action_create" in counts
        assert "failed" in counts


class TestAlertManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "alerts.json")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_alert(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        alert = manager.create_alert(
            level=AlertLevel.WARNING,
            alert_type=AlertType.TEST_FAILURE,
            title="Test Failure Alert",
            message="Test failed",
            source="test_runner",
            details={"test_name": "test1"},
        )
        
        assert alert.alert_id is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.status == AlertStatus.OPEN

    def test_acknowledge_alert(self):
        manager = AlertManager(storage_path=self.storage_path)
        alert = manager.create_alert(AlertLevel.CRITICAL, AlertType.SYSTEM_ERROR, "Test", "Test")
        
        updated = manager.acknowledge_alert(alert.alert_id, "user1")
        assert updated.status == AlertStatus.ACKNOWLEDGED
        assert updated.acknowledged_by == "user1"

    def test_resolve_alert(self):
        manager = AlertManager(storage_path=self.storage_path)
        alert = manager.create_alert(AlertLevel.WARNING, AlertType.TEST_FAILURE, "Test", "Test")
        
        updated = manager.resolve_alert(alert.alert_id, "user1")
        assert updated.status == AlertStatus.RESOLVED
        assert updated.resolved_by == "user1"

    def test_list_alerts_filtered(self):
        manager = AlertManager(storage_path=self.storage_path)
        manager.create_alert(AlertLevel.CRITICAL, AlertType.SYSTEM_ERROR, "Test", "Test")
        
        result = manager.list_alerts(level=AlertLevel.CRITICAL)
        assert result["total"] >= 1

    def test_evaluate_rules_kill_rate(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        alerts = manager.evaluate_rules({"kill_rate": 70})
        assert len(alerts) >= 1
        assert alerts[0].level == AlertLevel.WARNING

    def test_evaluate_rules_coverage(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        alerts = manager.evaluate_rules({"coverage": 75})
        assert len(alerts) >= 1

    def test_evaluate_rules_performance(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        alerts = manager.evaluate_rules({"avg_response_time_ms": 2500})
        assert len(alerts) >= 1

    def test_evaluate_rules_performance_critical(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        alerts = manager.evaluate_rules({"avg_response_time_ms": 6000})
        assert len(alerts) >= 1
        critical_alert = next(a for a in alerts if a.level == AlertLevel.CRITICAL)
        assert critical_alert is not None

    def test_get_alert_counts(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        counts = manager.get_alert_counts()
        assert "total" in counts
        assert "level_critical" in counts
        assert "status_open" in counts

    def test_list_rules(self):
        manager = AlertManager(storage_path=self.storage_path)
        
        rules = manager.list_rules()
        assert len(rules) >= 5


class TestNotificationManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "notifications.json")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_email_notifier_disabled(self):
        notifier = EmailNotifier()
        assert notifier.enabled is False

    def test_email_notifier_send_disabled(self):
        notifier = EmailNotifier()
        result = notifier.send("test@example.com", "Test", "Test body")
        assert result is False

    def test_dingtalk_notifier_disabled(self):
        notifier = DingTalkNotifier()
        assert notifier.enabled is False

    def test_dingtalk_notifier_send_disabled(self):
        notifier = DingTalkNotifier()
        result = notifier.send("Test", "Test message")
        assert result is False

    def test_feishu_notifier_disabled(self):
        notifier = FeishuNotifier()
        assert notifier.enabled is False

    def test_feishu_notifier_send_disabled(self):
        notifier = FeishuNotifier()
        result = notifier.send("Test", "Test message")
        assert result is False

    def test_send_notification_email_disabled(self):
        manager = NotificationManager(storage_path=self.storage_path)
        
        notification = manager.send_notification(
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            title="Test",
            message="Test message",
        )
        
        assert notification.status == "failed"

    def test_send_notification_dingtalk_disabled(self):
        manager = NotificationManager(storage_path=self.storage_path)
        
        notification = manager.send_notification(
            channel=NotificationChannel.DINGTALK,
            recipient="webhook",
            title="Test",
            message="Test message",
        )
        
        assert notification.status == "failed"

    def test_get_channel_status(self):
        manager = NotificationManager(storage_path=self.storage_path)
        
        status = manager.get_channel_status()
        assert "email" in status
        assert "dingtalk" in status
        assert "feishu" in status

    def test_generate_alert_message(self):
        manager = NotificationManager(storage_path=self.storage_path)
        alert = Alert(
            alert_id="test",
            level=AlertLevel.WARNING,
            alert_type=AlertType.TEST_FAILURE,
            title="Test Alert",
            message="Test message",
            source="test",
            details={"key": "value"},
        )
        
        message = manager.generate_alert_message(alert)
        assert "Test Alert" in message
        assert "WARNING" in message
        assert "key" in message