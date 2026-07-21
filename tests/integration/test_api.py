from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, run_test_pipeline
from src.models.contract import HttpRequest

client = TestClient(app)


class TestAPIEndpoints:
    def test_api_health_check(self):
        response = client.get("/")
        assert response.status_code == 404

    def test_api_docs_accessible(self):
        response = client.get("/docs")
        assert response.status_code == 200
        assert "TestAI Engine Service" in response.text

    @patch("src.api.main.run_test_pipeline")
    def test_execute_endpoint_success(self, mock_task):
        mock_result = MagicMock()
        mock_result.id = "test-task-id-123"
        mock_task.delay.return_value = mock_result

        request_data = {
            "step_id": "api_test_001",
            "description": "API Test",
            "protocol": "http",
            "method": "GET",
            "url": "https://example.com/api/test",
        }

        response = client.post("/execute", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["task_id"] == "test-task-id-123"
        assert len(data["trace_id"]) == 8
        assert "流水线已入队" in data["message"]

        mock_task.delay.assert_called_once()
        call_args = mock_task.delay.call_args
        assert call_args[0][1] == data["trace_id"]

    @patch("src.api.main.run_test_pipeline")
    def test_execute_endpoint_invalid_request(self, mock_task):
        invalid_data = {
            "step_id": "invalid_test",
            "description": "Invalid method",
            "protocol": "http",
            "method": "INVALID_METHOD",
            "url": "https://example.com",
        }

        response = client.post("/execute", json=invalid_data)

        assert response.status_code == 422
        mock_task.delay.assert_not_called()

    @patch("src.api.main.run_test_pipeline")
    def test_execute_endpoint_missing_required_fields(self, mock_task):
        incomplete_data = {"description": "Missing step_id"}

        response = client.post("/execute", json=incomplete_data)

        assert response.status_code == 422
        mock_task.delay.assert_not_called()

    @patch("src.api.main.run_test_pipeline")
    def test_execute_endpoint_with_headers(self, mock_task):
        mock_result = MagicMock()
        mock_result.id = "task-with-headers"
        mock_task.delay.return_value = mock_result

        request_data = {
            "step_id": "api_test_headers",
            "description": "Test with headers",
            "protocol": "http",
            "method": "POST",
            "url": "https://example.com/api/post",
            "headers": {"Authorization": "Bearer token123"},
            "body": {"key": "value"},
        }

        response = client.post("/execute", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"

    def test_http_request_model_validation(self):
        valid_request = HttpRequest(
            step_id="model_valid_test",
            description="Model validation",
            protocol="http",
            method="GET",
            url="https://example.com",
        )
        assert valid_request.step_id == "model_valid_test"
        assert valid_request.protocol == "http"

    def test_execute_endpoint_has_error_handling(self):
        import inspect

        from src.api.main import execute_test

        source = inspect.getsource(execute_test)
        assert "try" in source
        assert "except" in source
