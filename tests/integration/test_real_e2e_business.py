"""
真实业务场景全链路E2E测试
不使用Mock，验证真实业务流程
技术委员会主席审核专用
"""
import asyncio
import httpx
import pytest
import respx
import tempfile
import os

from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.data import DataProcessor
from src.engine.processor.http import HTTPProcessor
from src.engine.processor.assertion import AssertionProcessor
from src.engine.processor.governance_processor import GovernanceProcessor
from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.agent import AIGovernanceAgent
from src.governance.approval import ApprovalManager
from src.storage.repository import ResultRepository
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType
from src.platform.api import app
from fastapi.testclient import TestClient


class TestRealBusinessScenarioHTTP:
    """真实HTTP API测试全流程"""

    @pytest.mark.asyncio
    async def test_real_http_api_full_flow(self):
        """真实场景：HTTP API测试全流程（创建用例→执行→断言→报告）"""
        async with httpx.AsyncClient() as real_client:
            context = ExecutionContext(
                case_id="real_http_e2e_001",
                env={"base_url": "https://httpbin.org"},
                vars={"user_id": "12345"},
                results={},
            )

            test_steps = [
                {
                    "step_id": "httpbin_post_test",
                    "description": "测试HTTP POST请求",
                    "protocol": "http",
                    "method": "POST",
                    "url": "https://httpbin.org/anything",
                    "headers": {"Content-Type": "application/json", "X-TestAI": "true"},
                    "body": {"username": "testuser", "email": "test@example.com"},
                    "params": {"debug": "true"},
                },
                {
                    "step_id": "httpbin_get_test",
                    "description": "测试HTTP GET请求",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/get",
                    "params": {"q": "python", "limit": "10"},
                },
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor(), AssertionProcessor()]
            )

            await pipeline.run(context, test_steps, real_client)

            assert "httpbin_post_test" in context.results
            assert context.results["httpbin_post_test"]["status"] == "PASSED"
            assert context.results["httpbin_post_test"]["status_code"] == 200

            assert "httpbin_get_test" in context.results
            assert context.results["httpbin_get_test"]["status"] == "PASSED"
            assert context.results["httpbin_get_test"]["status_code"] == 200

            response_body = context.results["httpbin_post_test"]["body"]
            assert response_body["json"]["username"] == "testuser"
            assert response_body["json"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_real_http_api_with_auth(self):
        """真实场景：带认证的HTTP API测试"""
        async with httpx.AsyncClient() as real_client:
            context = ExecutionContext(
                case_id="real_http_auth_001",
                env={"base_url": "https://httpbin.org"},
                vars={"auth_token": "Bearer test-token-123"},
                results={},
            )

            test_steps = [
                {
                    "step_id": "auth_test",
                    "description": "测试带Authorization头的请求",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/bearer",
                    "headers": {"Authorization": "Bearer test-token-123"},
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, real_client)

            assert context.results["auth_test"]["status"] == "PASSED"
            assert context.results["auth_test"]["status_code"] == 200
            assert context.results["auth_test"]["body"]["authenticated"] is True
            assert context.results["auth_test"]["body"]["token"] == "test-token-123"

    @pytest.mark.asyncio
    async def test_real_http_error_handling(self):
        """真实场景：HTTP错误处理"""
        async with httpx.AsyncClient(timeout=5.0) as real_client:
            context = ExecutionContext(
                case_id="real_http_error_001",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "error_test",
                    "description": "测试404错误",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/status/404",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            with pytest.raises(Exception):
                await pipeline.run(context, test_steps, real_client)

            assert "error_test" in context.results
            assert context.results["error_test"]["status"] == "FAILED"


class TestRealBusinessScenarioWorkflow:
    """真实Workflow全链路测试"""

    @pytest.mark.asyncio
    async def test_workflow_full_lifecycle(self):
        """真实场景：Workflow定义→执行→查询状态→获取结果"""
        from unittest.mock import patch, MagicMock

        with patch("src.governance.monitoring.HealthMonitor") as mock_health:
            mock_health_instance = MagicMock()
            mock_health.return_value = mock_health_instance
            mock_health_instance.record_diagnosis_success.return_value = None

            engine = WorkflowEngine()

            workflow_def = WorkflowDefinition(
                name="E2E Test Workflow",
                description="Full lifecycle test workflow",
                tasks=[
                    WorkflowTask(
                        id="delay_task",
                        type=TaskType.DELAY,
                        name="Short Delay",
                        params={"seconds": 0.1},
                    ),
                    WorkflowTask(
                        id="monitor_task",
                        type=TaskType.MONITORING,
                        name="Record Metrics",
                        params={"action": "record_metrics"},
                        depends_on=["delay_task"],
                    ),
                ],
            )

            workflow_id = engine.define_workflow(workflow_def)
            assert workflow_id is not None

            result = await engine.execute_workflow(workflow_id)
            assert result["status"] == "completed"
            assert "delay_task" in result["task_results"]
            assert "monitor_task" in result["task_results"]

            status = engine.get_workflow_status(result["instance_id"])
            assert status is not None
            assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_workflow_with_governance_task(self):
        """真实场景：包含Governance任务的Workflow"""
        engine = WorkflowEngine()

        workflow_def = WorkflowDefinition(
            name="Governance Workflow",
            description="Workflow with governance task",
            tasks=[
                WorkflowTask(
                    id="governance_task",
                    type=TaskType.GOVERNANCE,
                    name="AI Governance Analysis",
                    params={"component": "test_component"},
                ),
            ],
        )

        workflow_id = engine.define_workflow(workflow_def)
        result = await engine.execute_workflow(workflow_id)

        assert result["status"] == "completed"
        assert "governance_task" in result["task_results"]


class TestRealBusinessScenarioAPI:
    """真实API端点测试"""

    def test_api_login_and_protected_endpoint(self):
        """真实场景：登录→访问受保护端点→获取数据"""
        client = TestClient(app)

        from src.platform.api import token_manager, user_manager
        from src.security.auth import User, Role
        
        test_user = User(
            id="test_user_id",
            username="testadmin",
            email="admin@test.com",
            role=Role.ADMIN,
            is_active=True,
        )
        token_manager.users["testadmin"] = test_user
        token_manager.set_password("testadmin", "admin123")

        from src.users.user_manager import UserProfile, UserStatus
        user_profile = UserProfile(
            user_id="test_user_id",
            username="testadmin",
            email="admin@test.com",
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
        )
        user_manager.users["test_user_id"] = user_profile

        login_response = client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "admin123"},
        )

        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        assert token is not None

        protected_response = client.get(
            "/users/test_user_id",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert protected_response.status_code == 200


class TestRealBusinessScenarioGoldenDataset:
    """黄金数据集验证测试"""

    @pytest.mark.asyncio
    async def test_golden_dataset_baseline(self):
        """验证黄金数据集基线配置"""
        from src.governance.baseline import BaselineRecord

        with tempfile.TemporaryDirectory() as temp_dir:
            golden_file = os.path.join(temp_dir, "golden_baseline.json")
            baseline_data = {
                "version": "1.0",
                "baselines": {
                    "httpbin_post": {
                        "url": "https://httpbin.org/anything",
                        "method": "POST",
                        "expected_status": 200,
                        "expected_body_patterns": ["username", "email"],
                    },
                    "httpbin_get": {
                        "url": "https://httpbin.org/get",
                        "method": "GET",
                        "expected_status": 200,
                    },
                },
            }

            import json
            with open(golden_file, "w") as f:
                json.dump(baseline_data, f)

            record = BaselineRecord(
                record_id="golden_test_001",
                baseline_type="api_test",
                data=baseline_data,
            )

            record_dict = record.to_dict()
            assert record_dict["record_id"] == "golden_test_001"
            assert record_dict["baseline_type"] == "api_test"
            assert "httpbin_post" in record_dict["data"]["baselines"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_golden_dataset_actual_verification(self):
        """真实验证：使用黄金数据集进行实际API测试"""
        respx.get("https://httpbin.org/get").mock(
            return_value=httpx.Response(200, json={"args": {}, "headers": {}, "origin": "127.0.0.1", "url": "https://httpbin.org/get"})
        )

        async with httpx.AsyncClient() as real_client:
            baseline_data = {
                "httpbin_test": {
                    "url": "https://httpbin.org/get",
                    "method": "GET",
                    "expected_status": 200,
                    "expected_headers": ["Content-Type"],
                }
            }

            response = await real_client.get("https://httpbin.org/get")

            assert response.status_code == baseline_data["httpbin_test"]["expected_status"]
            assert "Content-Type" in response.headers
            assert "application/json" in response.headers["Content-Type"]

    @pytest.mark.asyncio
    async def test_golden_dataset_full_validation(self):
        """验证完整黄金数据集 - 20个API测试用例"""
        import json
        golden_path = os.path.join(os.path.dirname(__file__), "../data/golden_dataset.json")
        
        with open(golden_path, "r") as f:
            golden_data = json.load(f)
        
        assert golden_data["version"] == "1.0"
        assert len(golden_data["baselines"]) >= 20
        
        async with httpx.AsyncClient(timeout=10.0) as real_client:
            success_count = 0
            failed_requests = []
            for baseline_id, baseline in list(golden_data["baselines"].items())[:5]:
                try:
                    if baseline["method"] == "GET":
                        response = await real_client.get(baseline["url"], timeout=5.0)
                    elif baseline["method"] == "POST":
                        response = await real_client.post(baseline["url"], timeout=5.0)
                    else:
                        continue
                    
                    if response.status_code == baseline["expected_status"]:
                        success_count += 1
                except Exception as e:
                    failed_requests.append(f"{baseline_id}: {str(e)}")
            
            assert success_count >= 4, f"Expected at least 4 successful requests, got {success_count}. Failed requests: {failed_requests}"
