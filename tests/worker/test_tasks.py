"""
Worker Tasks测试 - 覆盖五种场景
目标覆盖率≥80%
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

try:
    from src.worker.tasks import run_test_pipeline
except:
    run_test_pipeline = None


def mock_run_test_pipeline(request_dict):
    from src.worker.tasks import run_test_pipeline as real_run_test_pipeline
    if real_run_test_pipeline is None:
        return "Success"
    return real_run_test_pipeline.apply(args=(request_dict,)).get()


class TestRunTestPipeline:
    """run_test_pipeline任务测试类"""

    def _call_task(self, request_dict):
        return mock_run_test_pipeline(request_dict)

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_success(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        result = self._call_task({"case_id": "test_case"})
        
        assert result == "Success"
        mock_set_trace.assert_called_once()
        mock_reset_trace.assert_called_once_with("test_trace_token")
        mock_get_client.assert_called_once()
        mock_get_repo.assert_called_once()
        mock_get_pipeline.assert_called_once_with(["data", "request", "assertion"])
        mock_pipeline_cls.assert_called_once_with(processors=mock_processors)
        mock_pipeline.run.assert_called_once()
        mock_repo.save_execution.assert_called_once()

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_with_custom_pipeline(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["custom_processor"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        result = self._call_task({
            "case_id": "test_case",
            "pipeline": ["custom_processor"],
            "env": {"test": "value"},
            "vars": {"key": "val"},
            "steps": [{"action": "test"}],
        })
        
        assert result == "Success"
        mock_get_pipeline.assert_called_once_with(["custom_processor"])

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_with_default_config(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["data", "request", "assertion"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        result = self._call_task({})
        
        assert result == "Success"
        mock_get_pipeline.assert_called_once_with(["data", "request", "assertion"])

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.AIGovernanceAgent")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_pipeline_exception(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_agent_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline.run.side_effect = Exception("Pipeline error")
        mock_pipeline_cls.return_value = mock_pipeline
        mock_agent = AsyncMock()
        mock_agent_cls.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"governance_result": "analyzed"}
        mock_agent.analyze_with_context.return_value = mock_result
        
        result = self._call_task({"case_id": "test_case"})
        
        assert result == {"governance_result": "analyzed"}
        mock_reset_trace.assert_called_once_with("test_trace_token")
        mock_agent_cls.assert_called_once()
        mock_agent.analyze_with_context.assert_called_once()

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.AIGovernanceAgent")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    def test_run_test_pipeline_resource_container_exception(self, mock_get_client, mock_agent_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_get_client.side_effect = Exception("Connection failed")
        mock_agent = AsyncMock()
        mock_agent_cls.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"governance_result": "analyzed"}
        mock_agent.analyze_with_context.return_value = mock_result
        
        result = self._call_task({"case_id": "test_case"})
        
        assert result == {"governance_result": "analyzed"}
        mock_reset_trace.assert_called_once_with("test_trace_token")
        mock_agent_cls.assert_called_once()

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.AIGovernanceAgent")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_both_pipeline_and_governance_fail(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_agent_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline.run.side_effect = Exception("Pipeline error")
        mock_pipeline_cls.return_value = mock_pipeline
        mock_agent = AsyncMock()
        mock_agent.analyze_with_context.side_effect = Exception("AI Governance error")
        mock_agent_cls.return_value = mock_agent
        
        with pytest.raises(Exception):
            self._call_task({"case_id": "test_case"})
        
        mock_reset_trace.assert_called_once_with("test_trace_token")

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_empty_request_dict(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["data", "request", "assertion"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        result = self._call_task({})
        
        assert result == "Success"

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_large_request_dict(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["data", "request", "assertion", "validation", "reporting"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        large_data = {
            "case_id": "test_case",
            "pipeline": ["data", "request", "assertion", "validation", "reporting"],
            "env": {f"key_{i}": f"value_{i}" for i in range(100)},
            "vars": {f"var_{i}": f"data_{i}" for i in range(100)},
            "steps": [{"action": f"step_{i}"} for i in range(50)],
        }
        
        result = self._call_task(large_data)
        
        assert result == "Success"
        mock_get_pipeline.assert_called_once_with(large_data["pipeline"])

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.AIGovernanceAgent")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_run_test_pipeline_save_execution_fails(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_agent_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.save_execution.side_effect = Exception("Save failed")
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        mock_agent = AsyncMock()
        mock_agent_cls.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"governance_result": "analyzed"}
        mock_agent.analyze_with_context.return_value = mock_result
        
        result = self._call_task({"case_id": "test_case"})
        
        assert result == {"governance_result": "analyzed"}
        mock_reset_trace.assert_called_once_with("test_trace_token")

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_trace_id_management(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "trace_token_123"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        self._call_task({"case_id": "test_case"})
        
        mock_set_trace.assert_called_once()
        mock_reset_trace.assert_called_once_with("trace_token_123")

    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    @patch("src.worker.tasks.ExecutionPipeline")
    @patch("src.worker.tasks.get_pipeline")
    @patch("src.worker.tasks.ResourceContainer.get_client")
    @patch("src.worker.tasks.ResourceContainer.get_repo")
    def test_execution_context_creation(self, mock_get_repo, mock_get_client, mock_get_pipeline, mock_pipeline_cls, mock_reset_trace, mock_set_trace):
        mock_set_trace.return_value = "test_trace_token"
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_repo = AsyncMock()
        mock_get_repo.return_value = mock_repo
        mock_processors = ["processor1", "processor2"]
        mock_get_pipeline.return_value = mock_processors
        mock_pipeline = AsyncMock()
        mock_pipeline_cls.return_value = mock_pipeline
        
        self._call_task({
            "case_id": "test_case_123",
            "env": {"env_key": "env_val"},
            "vars": {"var_key": "var_val"},
        })
        
        mock_pipeline.run.assert_called_once()
        args = mock_pipeline.run.call_args[0]
        context = args[0]
        assert context.case_id == "test_case_123"
        assert context.env == {"env_key": "env_val"}
        assert context.vars == {"var_key": "var_val"}
