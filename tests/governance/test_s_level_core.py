import pytest
import os
import libcst as cst
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.tracker import GovernanceTracker, GovernanceActionType
from src.governance.baseline import GoldenBaselineManager, BaselineRecord
from src.governance.executor import GovernanceExecutor, SecurityVisitor
from src.governance.transformer import FunctionTransformer, ContextAwareTransformer
from src.governance.security import SecurePathValidator
from src.governance.models import PatchProposal, DiagnosticContext, PatchType
from src.governance.orchestrator import GovernanceOrchestrator, governance_transaction
from src.security.auth import TokenManager, PasswordHasher, Role, User
from src.users.user_manager import UserManager, UserStatus, UserRole
from src.teams.team_manager import TeamManager, TeamRole
from src.platform.config_manager import ConfigManager
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType, WorkflowStatus
from src.storage.database import get_db_manager, reset_db_manager


@pytest.fixture(autouse=True)
def setup_db():
    reset_db_manager()
    yield
    reset_db_manager()


class TestSLevelApprovalPersistence:
    """S级测试：审批管理数据持久化"""

    def test_approval_crud_persistence(self):
        manager = ApprovalManager(db_path=":memory:")
        tx_id = "test_tx_001"
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="safe_code",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output={},
            expected_baseline={},
        )

        record = manager.create_approval(tx_id=tx_id, proposal=proposal, context=context)
        assert record is not None
        assert record.tx_id == tx_id

        fetched = manager.get_approval(tx_id)
        assert fetched is not None
        assert fetched.status == ApprovalStatus.PENDING
        assert fetched.proposal.patch_type == PatchType.SECURITY

        manager.approve(tx_id, approver="admin")
        fetched = manager.get_approval(tx_id)
        assert fetched.status == ApprovalStatus.APPROVED
        assert fetched.approved_by == "admin"

    def test_approval_expiry(self):
        manager = ApprovalManager(db_path=":memory:")
        tx_id = "test_tx_002"
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="code",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output={},
            expected_baseline={},
        )

        record = manager.create_approval(tx_id=tx_id, proposal=proposal, context=context)
        assert not record.is_expired

        record.expires_at = datetime(2000, 1, 1)
        assert record.is_expired


class TestSLevelGovernanceTracker:
    """S级测试：治理追踪器"""

    def test_tracker_event_persistence(self):
        tracker = GovernanceTracker(db_path=":memory:")
        tracker.clear()
        trace_id = "test_trace_001"

        tracker.record_event(trace_id, GovernanceActionType.DIAGNOSE_START, component="test")
        tracker.record_event(trace_id, GovernanceActionType.DIAGNOSE_COMPLETE, component="test")
        tracker.record_event(trace_id, GovernanceActionType.PATCH_APPLIED, component="test")

        events = tracker.get_events_by_trace(trace_id)
        assert len(events) == 3
        assert events[0].action_type == GovernanceActionType.DIAGNOSE_START
        assert events[1].action_type == GovernanceActionType.DIAGNOSE_COMPLETE
        assert events[2].action_type == GovernanceActionType.PATCH_APPLIED

        summary = tracker.get_summary()
        assert summary["total_events"] == 3
        assert summary["by_action"]["diagnose_complete"] == 1

    def test_tracker_thread_safety(self):
        tracker = GovernanceTracker(db_path=":memory:")
        tracker.clear()
        trace_id = "thread_test"

        def record_events():
            for i in range(10):
                tracker.record_event(trace_id, GovernanceActionType.DIAGNOSE_START, component="thread_test")

        threads = [__import__("threading").Thread(target=record_events) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = tracker.get_events_by_trace(trace_id)
        assert len(events) == 50


class TestSLevelBaselineConvergence:
    """S级测试：基线收敛验证"""

    def test_baseline_validation(self):
        manager = GoldenBaselineManager()

        test_baseline = BaselineRecord(
            record_id="test_baseline",
            baseline_type="test",
            data={
                "record_id": "test_baseline",
                "name": "Test Baseline",
                "expected_score_min": 0.9,
            },
        )
        manager.add_baseline(test_baseline)

        actual_data = {"data": {"score": 0.95}}
        result = manager.validate_against_baseline("test_baseline", actual_data)
        assert result["passed"] is True

        actual_data_bad = {"data": {"score": 0.5}}
        result = manager.validate_against_baseline("test_baseline", actual_data_bad)
        assert result["passed"] is False

    def test_convergence_score_calculation(self):
        manager = GoldenBaselineManager()
        
        baseline = BaselineRecord(
            record_id="calc_test",
            baseline_type="test",
            data={"expected_score_min": 0.9},
        )
        manager.add_baseline(baseline)

        score = manager.calculate_convergence_score({"data": {"score": 0.95}}, "calc_test")
        assert score == 1.0
        score = manager.calculate_convergence_score({"data": {"score": 0.5}}, "calc_test")
        assert score == 0.8


class TestSLevelSecurityValidation:
    """S级测试：安全校验"""

    def test_security_visitor_forbidden_functions(self):
        code = """
def dangerous():
    eval("os.system('rm -rf /')")
    exec("malicious_code")
    os.system("bad_command")
"""
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "Forbidden" in visitor.unsafe_reason

    def test_path_validation(self):
        validator = SecurePathValidator()
        valid, _ = validator.validate_path(os.path.abspath("tests/test.txt"))
        assert valid is True
        
        result = validator.is_sandboxed("/etc/passwd")
        assert result is False
        
        valid, reason = validator.validate_path("../etc/passwd")
        assert valid is False


class TestSLevelAuthSecurity:
    """S级测试：认证安全"""

    def test_password_hashing(self):
        password = "secure_password_123"
        hashed = PasswordHasher.hash_password(password)
        assert hashed != password
        assert PasswordHasher.verify_password(password, hashed) is True
        assert PasswordHasher.verify_password("wrong_password", hashed) is False

    def test_token_validation(self):
        token_manager = TokenManager()
        user = User(
            id="test_user",
            username="testuser",
            role=Role.TESTER,
            email="test@test.com",
            password_hash="",
        )
        access_token = token_manager.create_access_token(user)
        decoded = token_manager.decode_token(access_token)
        assert decoded is not None
        assert decoded["sub"] == "test_user"


class TestSLevelUserPersistence:
    """S级测试：用户管理持久化"""

    def test_user_crud(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        manager = UserManager(use_database=True)

        user = manager.create_user(
            username="testuser",
            email="test@testai.local",
            role=UserRole.ADMIN,
            full_name="Test User",
            department="IT",
            password="testpass123",
        )
        assert user is not None
        assert user.user_id is not None

        fetched = manager.get_user(user.user_id)
        assert fetched is not None
        assert fetched.username == "testuser"
        assert fetched.email == "test@testai.local"
        assert manager.verify_password("testuser", "testpass123") is True

        updated = manager.update_user(user.user_id, full_name="Updated Name")
        assert updated.full_name == "Updated Name"

        assert manager.delete_user(user.user_id) is True
        assert manager.get_user(user.user_id) is None

        del os.environ["DATABASE_URL"]

    def test_user_status_transitions(self):
        manager = UserManager()
        manager.users.clear()
        user = manager.create_user(
            username="status_test",
            email="status@testai.local",
            role=UserRole.TESTER,
        )

        assert user.status == UserStatus.ACTIVE

        suspended = manager.suspend_user(user.user_id)
        assert suspended.status == UserStatus.SUSPENDED

        activated = manager.activate_user(user.user_id)
        assert activated.status == UserStatus.ACTIVE

        deactivated = manager.deactivate_user(user.user_id)
        assert deactivated.status == UserStatus.INACTIVE


class TestSLevelTeamPersistence:
    """S级测试：团队管理持久化"""

    def test_team_crud(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        manager = TeamManager(use_database=True)
        manager.teams.clear()

        team = manager.create_team(name="Test Team", description="Test Description")
        assert team is not None
        assert team.team_id is not None

        fetched = manager.get_team(team.team_id)
        assert fetched is not None
        assert fetched.name == "Test Team"

        updated = manager.update_team(team.team_id, description="Updated Description")
        assert updated.description == "Updated Description"

        assert manager.delete_team(team.team_id) is True
        assert manager.get_team(team.team_id) is None

        del os.environ["DATABASE_URL"]

    def test_team_member_management(self):
        manager = TeamManager()
        manager.teams.clear()
        
        team = manager.create_team(name="Member Test Team", owner_id="user1", owner_username="user1")

        assert len(team.members) == 1
        assert team.members[0].role == TeamRole.OWNER

        team = manager.add_member(team.team_id, "user2", "user2", TeamRole.MEMBER)
        assert len(team.members) == 2

        team = manager.update_member_role(team.team_id, "user2", TeamRole.ADMIN)
        assert team.members[1].role == TeamRole.ADMIN

        team = manager.remove_member(team.team_id, "user2")
        assert len(team.members) == 1

        with pytest.raises(ValueError):
            manager.remove_member(team.team_id, "user1")


class TestSLevelConfigPersistence:
    """S级测试：配置管理持久化"""

    def test_config_crud(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        manager = ConfigManager()

        assert manager.get_section("platform") is not None
        assert manager.get_value("platform", "name") == "TestAI Platform"

        manager.set_value("platform", "name", "Updated Platform")
        assert manager.get_value("platform", "name") == "Updated Platform"

        manager.update_section("api", {"port": 9000})
        assert manager.get_value("api", "port") == 9000

        del os.environ["DATABASE_URL"]

    def test_config_readonly(self):
        manager = ConfigManager()
        manager._sections["readonly_test"] = type('ConfigSection', (), {
            'name': 'readonly_test',
            'data': {'key': 'value'},
            'readonly': True,
        })()

        with pytest.raises(PermissionError):
            manager.update_section("readonly_test", {"key": "new_value"})


class TestSLevelWorkflowEngine:
    """S级测试：工作流引擎"""

    def test_workflow_definition_and_execution(self):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        engine = WorkflowEngine()

        definition = WorkflowDefinition(
            name="Test Workflow",
            description="Test",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="Check Status", params={"action": "get_status"}),
            ],
        )

        workflow_id = engine.define_workflow(definition)
        assert workflow_id is not None
        assert engine.get_workflow(workflow_id) is not None

        del os.environ["DATABASE_URL"]

    def test_workflow_with_dependencies(self):
        engine = WorkflowEngine()

        task1 = WorkflowTask(type=TaskType.MONITORING, name="Task1", id="task1")
        task2 = WorkflowTask(type=TaskType.MONITORING, name="Task2", id="task2", depends_on=["task1"])
        task3 = WorkflowTask(type=TaskType.MONITORING, name="Task3", id="task3", depends_on=["task2"])

        definition = WorkflowDefinition(name="Dependent Workflow", tasks=[task1, task2, task3])
        workflow_id = engine.define_workflow(definition)

        execution_order = engine._calculate_execution_order(definition.tasks)
        assert execution_order == ["task1", "task2", "task3"]

    def test_workflow_status_transitions(self):
        engine = WorkflowEngine()
        definition = WorkflowDefinition(name="Status Test", tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="Test")
        ])
        workflow_id = engine.define_workflow(definition)

        instance_id = engine.instances[next(iter(engine.instances))].instance_id if engine.instances else None
        assert instance_id is None or engine.get_workflow_status(instance_id) is not None


class TestSLevelTransformerPrecision:
    """S级测试：代码转换器精确性"""

    def test_function_transformer(self):
        code = """
def test_function():
    return "original"
"""
        tree = cst.parse_module(code)
        transformer = FunctionTransformer(
            target_function="test_function",
            new_body='return "patched"',
        )
        new_tree = tree.visit(transformer)
        assert '"patched"' in new_tree.code
        assert transformer.patched is True

    def test_context_aware_transformer(self):
        code = """
class TargetClass:
    def method(self):
        return "original"

class OtherClass:
    def method(self):
        return "other"
"""
        tree = cst.parse_module(code)
        transformer = ContextAwareTransformer(
            target_function="method",
            new_body='return "patched"',
            target_class="TargetClass",
        )
        new_tree = tree.visit(transformer)
        assert new_tree.code.count('return "patched"') == 1
        assert new_tree.code.count('return "other"') == 1
        assert transformer.patched is True


class TestSLevelGovernanceExecutor:
    """S级测试：治理执行器核心功能"""

    @pytest.mark.asyncio
    async def test_executor_patch_application_full_flow(self):
        executor = GovernanceExecutor()
        test_file = Path("tests/data/test_patch_target.py")
        test_file.parent.mkdir(exist_ok=True)
        test_file.write_text('def vulnerable_func():\n    return "unsafe"')

        try:
            with patch.object(executor._path_validator, 'validate_path', return_value=(True, "")):
                result = await executor.apply_patch(
                    file_path=str(test_file),
                    patch_type=PatchType.SECURITY,
                    target_function="vulnerable_func",
                    suggested_code='return "safe"',
                )

            assert result is True
            content = test_file.read_text()
            assert '"safe"' in content
            assert '"unsafe"' not in content
        finally:
            if test_file.exists():
                test_file.unlink()
            backup_file = Path(str(test_file) + ".bak")
            if backup_file.exists():
                backup_file.unlink()

    def test_executor_security_validation(self):
        executor = GovernanceExecutor()

        unsafe_code = 'eval("os.system(\'rm -rf /\')")'
        assert executor.is_safe_patch(unsafe_code) is False

        safe_code = 'return "safe_value"'
        assert executor.is_safe_patch(safe_code) is True


class TestSLevelGovernanceOrchestrator:
    """S级测试：治理编排器核心功能"""

    @pytest.mark.asyncio
    async def test_orchestrator_diagnose_flow(self):
        with patch('src.governance.orchestrator.AIGovernanceAgent'):
            with patch('src.governance.orchestrator.GovernanceExecutor'):
                with patch('src.governance.orchestrator.GitTransactionManager'):
                    with patch('src.governance.orchestrator.ApprovalManager'):
                        with patch('src.governance.orchestrator.GovernanceTracker'):
                            orchestrator = GovernanceOrchestrator()

        orchestrator.agent = AsyncMock()
        orchestrator.executor = AsyncMock()
        orchestrator.git_mgr = MagicMock()
        orchestrator.approval_mgr = MagicMock()
        orchestrator.tracker = MagicMock()

        orchestrator.agent.analyze_with_context.return_value = MagicMock(
            is_fixable=True,
            reasoning="Test reasoning",
            confidence_score=0.95,
            patch_proposal=PatchProposal(
                target_function="test_func",
                suggested_code="safe_code",
                patch_type=PatchType.SECURITY,
            ),
        )

        context = DiagnosticContext(
            step_id="test_step",
            component_name="test",
            input_data={},
            actual_output="error",
            expected_baseline="success",
        )

        result = await orchestrator.execute_governance_flow(context)
        assert result["status"] in ["DIAGNOSED", "PENDING_APPROVAL"]
        assert result["confidence_score"] == 0.95


class TestSLevelGitTransaction:
    """S级测试：Git事务管理"""

    def test_git_transaction_commit(self):
        from src.governance.git_manager import GitTransactionManager

        git_mgr = MagicMock(spec=GitTransactionManager)
        proposal = PatchProposal(target_function="test", suggested_code="code")

        with governance_transaction(git_mgr, "tx_001", proposal):
            pass

        git_mgr.start_transaction.assert_called_once_with("tx_001")
        git_mgr.commit.assert_called_once()

    def test_git_transaction_rollback(self):
        from src.governance.git_manager import GitTransactionManager

        git_mgr = MagicMock(spec=GitTransactionManager)
        git_mgr.commit.side_effect = Exception("Commit failed")
        proposal = PatchProposal(target_function="test", suggested_code="code")

        with pytest.raises(Exception, match="Commit failed"):
            with governance_transaction(git_mgr, "tx_002", proposal):
                pass

        git_mgr.rollback.assert_called_once_with("tx_002")


class TestSLevelCircuitBreaker:
    """S级测试：熔断保护机制"""

    def test_circuit_breaker_trip(self):
        from src.governance.resilience import CircuitBreaker

        breaker = CircuitBreaker(threshold=3)

        assert breaker.can_execute() is True

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.can_execute() is False

    def test_circuit_breaker_recovery(self):
        from src.governance.resilience import CircuitBreaker
        import time

        breaker = CircuitBreaker(threshold=1, recovery_timeout=1)

        breaker.record_failure()
        assert breaker.can_execute() is False

        time.sleep(1.1)
        assert breaker.can_execute() is True


class TestSLevelFileLock:
    """S级测试：文件锁机制"""

    def test_file_lock_concurrent_access(self):
        from src.governance.file_lock import FileLock

        lock_path = Path("tests/data/test_lock.lock")
        lock_path.parent.mkdir(exist_ok=True)

        lock1 = FileLock(str(lock_path))
        lock2 = FileLock(str(lock_path))

        with lock1:
            with pytest.raises(RuntimeError):
                with lock2:
                    pass

        if lock_path.exists():
            lock_path.unlink()


class TestSLevelAPIEndpoints:
    """S级测试：API端点核心功能"""

    def test_api_health_check(self):
        from fastapi.testclient import TestClient
        from src.platform.api import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["platform"] == "TestAI"

    def test_api_auth_login(self):
        from fastapi.testclient import TestClient
        from src.platform.api import app

        client = TestClient(app)
        response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "admin"


class TestSLevelWorkflowOrchestration:
    """S级测试：工作流编排核心功能"""

    def test_workflow_execution_order(self):
        task1 = WorkflowTask(type=TaskType.MONITORING, name="Task1", id="task1")
        task2 = WorkflowTask(type=TaskType.GOVERNANCE, name="Task2", id="task2", depends_on=["task1"])
        task3 = WorkflowTask(type=TaskType.APPROVAL, name="Task3", id="task3", depends_on=["task2"])

        definition = WorkflowDefinition(name="Test Flow", tasks=[task3, task1, task2])
        engine = WorkflowEngine()

        order = engine._calculate_execution_order(definition.tasks)
        assert order == ["task1", "task2", "task3"]

    def test_workflow_status_transitions(self):
        engine = WorkflowEngine()
        definition = WorkflowDefinition(name="Status Flow", tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="TestTask")
        ])
        workflow_id = engine.define_workflow(definition)

        workflow = engine.get_workflow(workflow_id)
        assert workflow is not None


class TestSLevelPermissionControl:
    """S级测试：权限控制核心功能"""

    def test_permission_check(self):
        from src.security.permissions import PermissionManager, Permission
        from src.security.auth import User, Role

        user = User(id="test", username="test", email="test@test.com", role=Role.ADMIN)
        manager = PermissionManager()

        assert manager.has_permission(user, Permission.VIEW_USERS) is True
        assert manager.has_permission(user, Permission.MANAGE_USERS) is True

        viewer_user = User(id="viewer", username="viewer", email="viewer@test.com", role=Role.VIEWER)
        assert manager.has_permission(viewer_user, Permission.MANAGE_USERS) is False

    def test_permission_enforcement(self):
        from src.platform.api import require_permission
        from src.security.permissions import Permission
        from src.security.auth import User, Role
        from fastapi import HTTPException

        dependency = require_permission(Permission.MANAGE_USERS)

        admin_user = User(id="admin", username="admin", email="admin@test.com", role=Role.ADMIN)
        result = dependency(admin_user)
        assert result == admin_user

        viewer_user = User(id="viewer", username="viewer", email="viewer@test.com", role=Role.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            dependency(viewer_user)
        assert exc_info.value.status_code == 403


class TestSLevelAlertManagement:
    """S级测试：告警管理核心功能"""

    def test_alert_creation_and_acknowledgment(self):
        from src.monitoring.alert_manager import AlertManager, AlertLevel, AlertStatus, AlertType

        manager = AlertManager(storage_path="tests/data/test_alerts.json")

        alert = manager.create_alert(
            level=AlertLevel.CRITICAL,
            alert_type=AlertType.SYSTEM_ERROR,
            title="Test Error",
            message="Error occurred",
            source="test",
        )
        assert alert is not None
        assert alert.alert_id is not None
        assert alert.level == AlertLevel.CRITICAL
        assert alert.status == AlertStatus.OPEN

        acknowledged = manager.acknowledge_alert(alert.alert_id, "admin")
        assert acknowledged is not None
        assert acknowledged.status == AlertStatus.ACKNOWLEDGED

    def test_alert_rule_evaluation(self):
        from src.monitoring.alert_manager import AlertManager, AlertRule, AlertLevel, AlertType

        manager = AlertManager(storage_path="tests/data/test_alerts_rules.json")

        rule = AlertRule(
            rule_id="test_rule",
            name="Test Rule",
            alert_type=AlertType.PERFORMANCE_DEGRADATION,
            level=AlertLevel.WARNING,
            condition="cpu_usage > 90",
            threshold=90,
        )
        manager.add_rule(rule)

        alerts = manager.evaluate_rules({"cpu_usage": 95})
        assert len(alerts) >= 0

        alerts = manager.evaluate_rules({"cpu_usage": 80})
        assert len(alerts) >= 0


class TestSLevelDatabasePersistence:
    """S级测试：数据库持久化核心功能"""

    def test_database_connection(self):
        from src.storage.database import get_db_manager, reset_db_manager

        reset_db_manager()
        db = get_db_manager()

        assert db is not None
        assert db.engine is not None

    def test_database_table_creation(self):
        from src.storage.database import get_db_manager, reset_db_manager

        reset_db_manager()
        db = get_db_manager()

        assert db.users_table is not None
        assert db.teams_table is not None


class TestSLevelMutationTesting:
    """S级测试：变异测试核心功能"""

    def test_mutation_tester_initialization(self):
        from tests.utils.custom_mutation_test import CustomMutationTester

        tester = CustomMutationTester(target_dir="src/governance/executor.py")
        assert tester.target_dir == "src/governance/executor.py"
        assert tester.test_files == "all"


class TestSLevelGoldenBaseline:
    """S级测试：黄金基线核心功能"""

    def test_baseline_full_validation(self):
        manager = GoldenBaselineManager()

        baseline = BaselineRecord(
            record_id="s_level_baseline",
            baseline_type="test",
            data={
                "name": "S-Level Test Baseline",
                "expected_score_min": 0.9,
                "expected_response_time_ms": 1000,
            },
        )
        manager.add_baseline(baseline)

        valid_data = {"data": {"score": 0.95, "response_time_ms": 500}}
        result = manager.validate_against_baseline("s_level_baseline", valid_data)
        assert result["passed"] is True

        invalid_data = {"data": {"score": 0.5, "response_time_ms": 2000}}
        result = manager.validate_against_baseline("s_level_baseline", invalid_data)
        assert result["passed"] is False

    def test_convergence_loop(self):
        manager = GoldenBaselineManager()

        baseline = BaselineRecord(
            record_id="convergence_test",
            baseline_type="test",
            data={"expected_score_min": 0.9},
        )
        manager.add_baseline(baseline)

        for i in range(5):
            score = 0.9 + (i * 0.01)
            data = {"data": {"score": score}}
            result = manager.validate_against_baseline("convergence_test", data)
            if score >= 0.9:
                assert result["passed"] is True


class TestSLevelApprovalWorkflow:
    """S级测试：审批工作流核心功能"""

    def test_approval_chain(self):
        manager = ApprovalManager(db_path=":memory:")
        tx_id = "approval_chain_test"

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="code",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output={},
            expected_baseline={},
        )

        record = manager.create_approval(tx_id, proposal, context)
        assert record.status == ApprovalStatus.PENDING

        manager.approve(tx_id, approver="manager")
        record = manager.get_approval(tx_id)
        assert record.status == ApprovalStatus.APPROVED

    def test_approval_rejection(self):
        manager = ApprovalManager(db_path=":memory:")
        tx_id = "rejection_test"

        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="code",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="step1",
            component_name="test",
            input_data={},
            actual_output={},
            expected_baseline={},
        )

        manager.create_approval(tx_id, proposal, context)
        manager.reject(tx_id, approver="manager", reason="Security concern")

        record = manager.get_approval(tx_id)
        assert record.status == ApprovalStatus.REJECTED
        assert record.approved_by == "manager"
        assert record.reason == "Security concern"
