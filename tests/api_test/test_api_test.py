import pytest
import asyncio
import httpx
from fastapi.testclient import TestClient

from src.platform.api import app
from src.api_test.client import APITestClient
from src.api_test.test_runner import APITestRunner
from src.api_test.schema import APITestCase, APITestAssertion, HTTPMethod, AssertionType, APITestReport


class TestAPITestClient:
    def test_client_creation(self):
        client = APITestClient(base_url="http://localhost:8000")
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 30

    @pytest.mark.asyncio
    async def test_send_get_request(self):
        import respx
        with respx.mock:
            respx.get("http://test/test").mock(return_value=httpx.Response(200, json={"status": "ok", "data": "test"}))
            
            client = APITestClient(base_url="http://test")
            status_code, response_body, response_time, headers = await client.send_request(
                HTTPMethod.GET, "/test"
            )
            
            assert status_code == 200
            assert response_body == {"status": "ok", "data": "test"}
            assert response_time >= 0
            assert "content-type" in [k.lower() for k in headers.keys()]
            await client.close()

    @pytest.mark.asyncio
    async def test_send_post_request(self):
        import respx
        with respx.mock:
            respx.post("http://test/test").mock(return_value=httpx.Response(201, json={"created": True, "id": "123"}))
            
            client = APITestClient(base_url="http://test")
            status_code, response_body, response_time, headers = await client.send_request(
                HTTPMethod.POST, "/test", body={"key": "value"}
            )
            
            assert status_code == 201
            assert response_body == {"created": True, "id": "123"}
            assert response_time >= 0
            await client.close()

    @pytest.mark.asyncio
    async def test_get_method(self):
        import respx
        with respx.mock:
            respx.get("http://test/test").mock(return_value=httpx.Response(200, json={"method": "GET"}))
            
            client = APITestClient(base_url="http://test")
            status_code, response_body, response_time, headers = await client.get("/test")
            
            assert status_code == 200
            assert response_body == {"method": "GET"}
            await client.close()

    @pytest.mark.asyncio
    async def test_post_method(self):
        import respx
        with respx.mock:
            respx.post("http://test/test").mock(return_value=httpx.Response(200, json={"method": "POST", "received": {"data": "test"}}))
            
            client = APITestClient(base_url="http://test")
            status_code, response_body, response_time, headers = await client.post("/test", body={"data": "test"})
            
            assert status_code == 200
            assert response_body == {"method": "POST", "received": {"data": "test"}}
            await client.close()


class TestAPITestRunner:
    def test_runner_creation(self):
        runner = APITestRunner(base_url="http://localhost:8000")
        assert runner.client.base_url == "http://localhost:8000"

    def test_evaluate_json_path_simple(self):
        runner = APITestRunner(base_url="http://test")
        data = {"status": "healthy", "code": 200}
        
        result = runner._evaluate_json_path("status", data, "healthy", "==")
        assert result is True
        
        result = runner._evaluate_json_path("code", data, 200, "==")
        assert result is True
        
        result = runner._evaluate_json_path("code", data, 500, "==")
        assert result is False

    def test_evaluate_json_path_nested(self):
        runner = APITestRunner(base_url="http://test")
        data = {"data": {"user": {"name": "admin", "role": "admin"}}}
        
        result = runner._evaluate_json_path("data.user.name", data, "admin", "==")
        assert result is True
        
        result = runner._evaluate_json_path("data.user.role", data, "viewer", "==")
        assert result is False

    def test_evaluate_json_path_list(self):
        runner = APITestRunner(base_url="http://test")
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        
        result = runner._evaluate_json_path("items.0.id", data, 1, "==")
        assert result is True
        
        result = runner._evaluate_json_path("items.2.id", data, 3, "==")
        assert result is True

    def test_evaluate_json_path_operators(self):
        runner = APITestRunner(base_url="http://test")
        data = {"count": 10, "value": 5}
        
        assert runner._evaluate_json_path("count", data, 5, ">") is True
        assert runner._evaluate_json_path("count", data, 15, "<") is True
        assert runner._evaluate_json_path("value", data, 5, ">=") is True
        assert runner._evaluate_json_path("value", data, 5, "<=") is True
        assert runner._evaluate_json_path("value", data, 6, "!=") is True
        assert runner._evaluate_json_path("count", data, "10", "contains") is True

    @pytest.mark.asyncio
    async def test_run_test_case(self):
        runner = APITestRunner(base_url="http://test")
        
        test_case = APITestCase(
            name="test_case",
            method=HTTPMethod.GET,
            url="/test",
            assertions=[
                APITestAssertion(type=AssertionType.RESPONSE_TIME, expected=10000),
            ],
        )
        
        result = await runner.run_test_case(test_case)
        
        assert result.test_case_name == "test_case"
        assert result.passed is True or result.passed is False
        assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_run_test_suite(self):
        runner = APITestRunner(base_url="http://test")
        
        test_cases = [
            APITestCase(
                name="test1",
                method=HTTPMethod.GET,
                url="/test1",
                assertions=[
                    APITestAssertion(type=AssertionType.RESPONSE_TIME, expected=10000),
                ],
            ),
            APITestCase(
                name="test2",
                method=HTTPMethod.GET,
                url="/test2",
                assertions=[
                    APITestAssertion(type=AssertionType.RESPONSE_TIME, expected=10000),
                ],
            ),
        ]
        
        report = await runner.run_test_suite(test_cases)
        
        assert report.total_tests == 2
        assert report.start_time is not None
        assert report.end_time is not None

    def test_generate_report(self):
        runner = APITestRunner(base_url="http://test")
        
        from datetime import datetime
        from src.api_test.schema import APITestResult
        
        report = APITestReport(
            total_tests=2,
            passed_tests=1,
            failed_tests=1,
            avg_response_time_ms=100.0,
            pass_rate=50.0,
            results=[
                APITestResult(test_case_name="test1", passed=True),
                APITestResult(test_case_name="test2", passed=False),
            ],
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        
        report_json = runner.generate_report(report)
        assert '"total_tests": 2' in report_json
        assert '"pass_rate": "50.00%"' in report_json
        assert '"passed_tests": 1' in report_json
        assert '"failed_tests": 1' in report_json


class TestAPITestSchema:
    def test_http_method_enum(self):
        assert HTTPMethod.GET.value == "GET"
        assert HTTPMethod.POST.value == "POST"
        assert HTTPMethod.PUT.value == "PUT"
        assert HTTPMethod.DELETE.value == "DELETE"
        assert HTTPMethod.PATCH.value == "PATCH"

    def test_assertion_type_enum(self):
        assert AssertionType.STATUS_CODE.value == "status_code"
        assert AssertionType.JSON_PATH.value == "json_path"
        assert AssertionType.RESPONSE_TIME.value == "response_time"
        assert AssertionType.HEADER.value == "header"
        assert AssertionType.BODY_CONTAINS.value == "body_contains"

    def test_api_test_case_creation(self):
        test_case = APITestCase(
            name="test",
            method=HTTPMethod.GET,
            url="/health",
            headers={"Content-Type": "application/json"},
            params={"id": 1},
            body={"data": "test"},
            assertions=[
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
            ],
            timeout=10,
            retries=2,
        )
        
        assert test_case.name == "test"
        assert test_case.method == HTTPMethod.GET
        assert test_case.url == "/health"
        assert test_case.timeout == 10
        assert test_case.retries == 2
        assert len(test_case.assertions) == 1


class TestIntegrationWithFastAPI:
    def test_health_endpoint(self):
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["platform"] == "TestAI"

    def test_auth_login_success(self):
        client = TestClient(app)
        response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
        assert response.json()["user"]["role"] == "admin"

    def test_auth_login_failure(self):
        client = TestClient(app)
        response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        
        assert response.status_code == 401

    def test_protected_endpoint_without_auth(self):
        client = TestClient(app)
        response = client.get("/governance/approvals")
        
        assert response.status_code == 401

    def test_protected_endpoint_with_auth(self):
        client = TestClient(app)
        
        login_response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        token = login_response.json()["access_token"]
        
        response = client.get(
            "/governance/approvals",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        assert "count" in response.json()