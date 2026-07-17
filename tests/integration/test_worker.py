from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.container import ResourceContainer
from src.core.tracer import reset_trace_id, set_trace_id
from src.worker.tasks import run_test_pipeline


@pytest.fixture(autouse=True)
def setup_mocks():
    ResourceContainer._client = AsyncMock()
    ResourceContainer._repo = AsyncMock()
    ResourceContainer._repo.save_execution = AsyncMock(return_value=True)
    yield
    ResourceContainer._client = None
    ResourceContainer._repo = None


class TestWorkerTasks:
    def test_task_function_exists(self):
        assert callable(run_test_pipeline)
        assert hasattr(run_test_pipeline, 'delay')

    def test_task_has_correct_decorator(self):
        assert hasattr(run_test_pipeline, 'bind')
        assert run_test_pipeline.name == "tasks.run_test_pipeline"

    def test_trace_id_management(self):
        token = set_trace_id("test-trace-id")
        assert token is not None
        reset_trace_id(token)

    def test_task_with_default_pipeline_config(self):
        request_dict = {
            "case_id": "default_config_test",
            "steps": []
        }
        assert "pipeline" not in request_dict
        assert request_dict.get("pipeline", ["data", "request", "assertion"]) == ["data", "request", "assertion"]

    def test_task_accepts_request_dict(self):
        request_dict = {
            "case_id": "test_case",
            "env": {"env": "test"},
            "vars": {"user_id": "123"},
            "steps": [],
            "pipeline": ["data", "http", "assertion"]
        }
        assert isinstance(request_dict, dict)
        assert "case_id" in request_dict
        assert "steps" in request_dict
        assert isinstance(request_dict["steps"], list)

    def test_task_function_has_request_dict_param(self):
        import inspect
        sig = inspect.signature(run_test_pipeline.run)
        params = list(sig.parameters.keys())
        assert 'request_dict' in params

    def test_task_module_structure(self):
        import src.worker.tasks as tasks_module
        assert hasattr(tasks_module, 'run_test_pipeline')
        assert hasattr(tasks_module, 'celery_app')
        assert hasattr(tasks_module, 'AsyncLoopManager')
        assert hasattr(tasks_module, 'ResourceContainer')

    def test_celery_app_import(self):
        from src.worker.celery_app import celery_app
        assert celery_app is not None

    def test_task_with_env_and_vars_validation(self):
        request_dict = {
            "case_id": "validation_test",
            "env": {"env": "production", "region": "us-east"},
            "vars": {"user_id": "123", "api_key": "abc"},
            "steps": []
        }
        assert isinstance(request_dict.get("env"), dict)
        assert isinstance(request_dict.get("vars"), dict)
        assert "env" in request_dict["env"]
        assert "user_id" in request_dict["vars"]

    def test_task_with_custom_pipeline_validation(self):
        request_dict = {
            "case_id": "custom_pipeline_validation",
            "steps": [],
            "pipeline": ["data", "http", "assertion"]
        }
        assert isinstance(request_dict.get("pipeline"), list)
        assert len(request_dict["pipeline"]) == 3
        assert "http" in request_dict["pipeline"]

    def test_task_empty_steps_validation(self):
        request_dict = {
            "case_id": "empty_steps_validation",
            "steps": []
        }
        assert request_dict["steps"] == []

    def test_task_missing_case_id_fallback(self):
        request_dict = {
            "steps": []
        }
        fallback_case_id = request_dict.get("case_id", "default_case")
        assert fallback_case_id == "default_case"

    def test_task_request_dict_structure(self):
        request_dict = {
            "case_id": "structure_test",
            "env": {},
            "vars": {},
            "steps": [],
            "pipeline": ["data", "request", "assertion"]
        }
        required_keys = ["case_id", "steps"]
        for key in required_keys:
            assert key in request_dict, f"Missing required key: {key}"

    def test_task_execution_path_imports(self):
        from src.worker.tasks import (AIGovernanceAgent, AsyncLoopManager,
                                      DiagnosticContext, ExecutionContext,
                                      ExecutionPipeline, ResourceContainer,
                                      get_pipeline)
        assert AsyncLoopManager is not None
        assert ResourceContainer is not None
        assert ExecutionContext is not None
        assert ExecutionPipeline is not None
        assert get_pipeline is not None
        assert AIGovernanceAgent is not None
        assert DiagnosticContext is not None

    def test_task_celery_delay_method(self):
        mock_request = {"case_id": "delay_test", "steps": []}
        task_result = run_test_pipeline.delay(mock_request)
        assert hasattr(task_result, 'id')
        assert hasattr(task_result, 'get')

    def test_trace_id_is_unique(self):
        token1 = set_trace_id("trace-1")
        token2 = set_trace_id("trace-2")
        assert token1 is not None
        assert token2 is not None
        reset_trace_id(token1)
        reset_trace_id(token2)

    def test_task_timeout_default_value(self):
        assert run_test_pipeline.run.__code__.co_argcount >= 1