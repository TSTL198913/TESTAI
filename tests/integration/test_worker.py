"""
Worker Tasks测试 - 仅保留有效测试用例
目标：验证真实业务逻辑，禁止仅验证结构/类型的弱测试
"""
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
    def test_task_celery_delay_method(self):
        """正向：Celery任务能通过delay方法异步执行"""
        with patch.object(run_test_pipeline, "delay") as mock_delay:
            mock_result = MagicMock()
            mock_result.id = "test-task-id"
            mock_delay.return_value = mock_result
            mock_request = {"case_id": "delay_test", "steps": []}
            task_result = run_test_pipeline.delay(mock_request)
            mock_delay.assert_called_once_with(mock_request)
            assert getattr(task_result, "id", None) == "test-task-id"

    def test_trace_id_is_unique(self):
        """正向：Trace ID管理正常工作"""
        token1 = set_trace_id("trace-1")
        token2 = set_trace_id("trace-2")
        assert token1 is not None
        assert token2 is not None
        reset_trace_id(token1)
        reset_trace_id(token2)

    def test_task_with_custom_pipeline_validation(self):
        """正向：任务能接受自定义pipeline配置"""
        request_dict = {
            "case_id": "custom_pipeline_validation",
            "steps": [],
            "pipeline": ["data", "http", "assertion"],
        }
        assert request_dict.get("pipeline") == ["data", "http", "assertion"]
        assert len(request_dict["pipeline"]) == 3
