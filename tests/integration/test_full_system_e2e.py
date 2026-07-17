import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.data import DataProcessor
from src.engine.processor.http import HTTPProcessor
from src.engine.processor.assertion import AssertionProcessor
from src.engine.processor.governance_processor import GovernanceProcessor
from src.core.context import ExecutionContext
from src.core.container import ResourceContainer
from src.governance.resilience import CircuitBreaker
from src.governance.agent import AIGovernanceAgent
from src.governance.orchestrator import GovernanceOrchestrator
from src.storage.repository import ResultRepository
from src.models.contract import HttpRequest, GrpcRequest, ExecutionCase
from src.models.result import StepResult


@pytest.fixture(autouse=True)
def setup_mocks():
    ResourceContainer._client = AsyncMock()
    ResourceContainer._repo = AsyncMock()
    yield
    ResourceContainer._client = None
    ResourceContainer._repo = None


class TestFullSystemE2E:
    def test_system_initialization(self):
        processors = [DataProcessor(), HTTPProcessor(), AssertionProcessor()]
        pipeline = ExecutionPipeline(processors=processors)
        assert len(pipeline.processors) == 3
        assert isinstance(pipeline.processors[0], DataProcessor)
        assert isinstance(pipeline.processors[1], HTTPProcessor)
        assert isinstance(pipeline.processors[2], AssertionProcessor)

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self):
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"success": True, "data": "test"}
        mock_client.request.return_value = mock_response

        processors = [DataProcessor(), HTTPProcessor(), AssertionProcessor()]
        pipeline = ExecutionPipeline(processors=processors)

        test_steps = [
            {
                "step_id": "e2e_test_001",
                "description": "Full pipeline test",
                "protocol": "http",
                "method": "GET",
                "url": "https://example.com/api/test",
                "params": {"id": "123"}
            }
        ]

        context = ExecutionContext(
            case_id="full_e2e_test",
            env={"env": "test"},
            vars={"user_id": "123"},
            results={}
        )

        processed_steps = await pipeline.run(context, test_steps, mock_client)

        assert len(processed_steps) == 1
        assert context.results["e2e_test_001"]["status"] == "PASSED"
        assert context.results["e2e_test_001"]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_variable_rendering_pipeline(self):
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"user": "test_user"}
        mock_client.request.return_value = mock_response

        processors = [DataProcessor(), HTTPProcessor()]
        pipeline = ExecutionPipeline(processors=processors)

        test_steps = [
            {
                "step_id": "var_render_001",
                "description": "Variable rendering test",
                "protocol": "http",
                "method": "GET",
                "url": "${base_url}/users/${user_id}",
                "params": {"token": "${api_token}"}
            }
        ]

        context = ExecutionContext(
            case_id="var_render_test",
            env={},
            vars={"base_url": "https://api.example.com", "user_id": "456", "api_token": "abc123"},
            results={}
        )

        await pipeline.run(context, test_steps, mock_client)

        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert "https://api.example.com/users/456" in str(call_args)

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self):
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = "Service Unavailable"
        mock_client.request.return_value = mock_response

        processors = [DataProcessor(), HTTPProcessor()]
        pipeline = ExecutionPipeline(processors=processors)

        test_steps = [
            {
                "step_id": "error_test_001",
                "description": "Error handling test",
                "protocol": "http",
                "method": "GET",
                "url": "https://example.com/api/fail"
            }
        ]

        context = ExecutionContext(
            case_id="error_handling_test",
            env={},
            vars={},
            results={}
        )

        with pytest.raises(Exception):
            await pipeline.run(context, test_steps, mock_client)

        assert context.results["error_test_001"]["status"] == "FAILED"

    def test_circuit_breaker_state_transition(self):
        breaker = CircuitBreaker(threshold=2, recovery_timeout=5)

        assert breaker.can_execute() is True
        assert breaker.state.value == "closed"

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.can_execute() is False
        assert breaker.state.value == "open"

    @pytest.mark.asyncio
    async def test_governance_orchestrator_flow(self):
        from src.governance.models import DiagnosticContext, PatchProposal

        mock_diagnosis = MagicMock()
        mock_diagnosis.reasoning = "Test analysis"
        mock_diagnosis.confidence_score = 0.95
        mock_diagnosis.is_fixable = False
        mock_diagnosis.patch_proposal = None

        mock_agent = AsyncMock(spec=AIGovernanceAgent)
        mock_agent.analyze_with_context.return_value = mock_diagnosis

        orchestrator = GovernanceOrchestrator()
        orchestrator.agent = mock_agent

        diag_context = DiagnosticContext(
            step_id="gov_test_001",
            component_name="test",
            input_data={"test": "data"},
            actual_output="result",
            expected_baseline=None,
            exception_trace=None
        )

        result = await orchestrator.execute_governance_flow(diag_context)

        assert result["status"] == "SKIPPED"
        assert result["confidence_score"] == 0.95

    def test_data_model_validation(self):
        http_request = HttpRequest(
            step_id="model_test_001",
            description="Model validation test",
            protocol="http",
            method="GET",
            url="https://example.com"
        )
        assert http_request.step_id == "model_test_001"
        assert http_request.method == "GET"

        grpc_request = GrpcRequest(
            step_id="grpc_model_test",
            description="gRPC test",
            protocol="grpc",
            proto_file_path="test.proto",
            service="TestService",
            method="TestMethod",
            payload={"key": "value"}
        )
        assert grpc_request.service == "TestService"

    @pytest.mark.asyncio
    async def test_repository_save_and_retrieve(self):
        mock_db = AsyncMock()
        mock_collection = AsyncMock()
        mock_db.execution_results = mock_collection
        mock_collection.insert_one.return_value = None

        repo = ResultRepository(db=mock_db)

        execution_data = {
            "case_id": "repo_test_001",
            "results": {"step1": {"status": "PASSED"}}
        }

        await repo.save_execution(execution_data["case_id"], execution_data["results"])

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert inserted_doc["step_id"] == "repo_test_001"
        assert inserted_doc["results"] == execution_data["results"]

    @pytest.mark.asyncio
    async def test_multi_step_pipeline(self):
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"success": True}
        mock_client.request.return_value = mock_response

        processors = [DataProcessor(), HTTPProcessor(), AssertionProcessor()]
        pipeline = ExecutionPipeline(processors=processors)

        test_steps = [
            {
                "step_id": "multi_step_001",
                "description": "Step 1",
                "protocol": "http",
                "method": "POST",
                "url": "https://example.com/api/login",
                "body": {"username": "test", "password": "pass"}
            },
            {
                "step_id": "multi_step_002",
                "description": "Step 2",
                "protocol": "http",
                "method": "GET",
                "url": "https://example.com/api/profile"
            },
            {
                "step_id": "multi_step_003",
                "description": "Step 3",
                "protocol": "http",
                "method": "GET",
                "url": "https://example.com/api/settings"
            }
        ]

        context = ExecutionContext(
            case_id="multi_step_test",
            env={},
            vars={},
            results={}
        )

        processed_steps = await pipeline.run(context, test_steps, mock_client)

        assert len(processed_steps) == 3
        assert mock_client.request.call_count == 3
        assert all(r["status"] == "PASSED" for r in context.results.values())

    def test_execution_case_serialization(self):
        case = ExecutionCase(
            case_id="case_serialization_test",
            name="Test Case",
            steps=[
                HttpRequest(
                    step_id="step1",
                    description="Test HTTP",
                    protocol="http",
                    method="GET",
                    url="https://example.com"
                )
            ]
        )

        case_dict = case.model_dump()
        assert case_dict["case_id"] == "case_serialization_test"
        assert case_dict["steps"][0]["protocol"] == "http"

        restored_case = ExecutionCase(**case_dict)
        assert restored_case.case_id == case.case_id
        assert restored_case.steps[0].step_id == "step1"

    @pytest.mark.asyncio
    async def test_context_isolation(self):
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"success": True}
        mock_client.request.return_value = mock_response

        processors = [DataProcessor(), HTTPProcessor()]
        pipeline = ExecutionPipeline(processors=processors)

        context1 = ExecutionContext(
            case_id="context_isolation_test_1",
            env={"env": "test1"},
            vars={"user": "user1"},
            results={}
        )

        context2 = ExecutionContext(
            case_id="context_isolation_test_2",
            env={"env": "test2"},
            vars={"user": "user2"},
            results={}
        )

        test_steps = [
            {
                "step_id": "isolation_step",
                "description": "Isolation test",
                "protocol": "http",
                "method": "GET",
                "url": "https://example.com/api/test"
            }
        ]

        await pipeline.run(context1, test_steps, mock_client)
        await pipeline.run(context2, test_steps, mock_client)

        assert context1.case_id != context2.case_id
        assert context1.env != context2.env
        assert context1.vars != context2.vars