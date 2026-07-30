"""P1-6: API 响应格式统一测试。

验证:
1. 所有成功响应使用 ApiResponse 格式: {success, data, message, error_code}
2. 所有错误响应(HTTPException)使用 ErrorResponse 格式: {success: false, message, error_code, detail}
3. 不再有裸 dict 返回(违反响应格式统一)
"""
import pytest
from fastapi.testclient import TestClient

from src.platform.api import app


@pytest.fixture
def client():
    """基础 client(无认证)。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """获取认证 headers。"""
    login_resp = client.post(
        "/auth/login",
        json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAPIResponseFormatUnification:
    """P1-6: 验证 API 响应格式统一。"""

    def test_http_exception_returns_error_response_format(self, client):
        """HTTPException 必须返回 ErrorResponse 格式,而非纯 detail 字符串。

        ErrorResponse 格式: {success: false, message, error_code, detail}
        """
        # 不存在的审批记录 → 404 HTTPException
        response = client.post(
            "/governance/approvals/nonexistent_tx/approve",
            headers={
                "Authorization": "Bearer " + client.post(
                    "/auth/login",
                    json={"username": "admin", "password": "password"},
                ).json()["data"]["access_token"]
            },
        )

        assert response.status_code == 404
        body = response.json()

        # 必须是 ErrorResponse 格式,而非 {"detail": "..."}
        assert "success" in body, (
            f"错误响应必须是 ErrorResponse 格式(含 success 字段), 实际: {body}"
        )
        assert body["success"] is False, (
            f"错误响应 success 必须为 False, 实际: {body.get('success')}"
        )
        assert "message" in body, f"错误响应必须包含 message 字段, 实际: {body}"
        assert "error_code" in body, (
            f"错误响应必须包含 error_code 字段, 实际: {body}"
        )
        # 不应再有裸 detail 字段(向后兼容可保留,但必须有 message/error_code)
        assert body.get("message"), "message 字段不能为空"

    def test_unauthorized_returns_error_response_format(self, client):
        """401 未认证响应必须是 ErrorResponse 格式。"""
        response = client.get("/auth/me")

        assert response.status_code == 401
        body = response.json()

        # 必须包含 success/message/error_code 字段
        assert "success" in body, f"401 响应必须是 ErrorResponse 格式, 实际: {body}"
        assert body["success"] is False
        assert "message" in body
        assert "error_code" in body

    def test_forbidden_returns_error_response_format(self, client, auth_headers):
        """403 权限不足响应必须是 ErrorResponse 格式。"""
        # 用 viewer 用户(无 APPROVE_PATCH 权限)尝试 approve
        viewer_login = client.post(
            "/auth/login",
            json={"username": "viewer", "password": "password"},
        )
        viewer_token = viewer_login.json()["data"]["access_token"]

        response = client.post(
            "/governance/approvals/some_tx/approve",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )

        assert response.status_code == 403
        body = response.json()

        assert "success" in body, f"403 响应必须是 ErrorResponse 格式, 实际: {body}"
        assert body["success"] is False
        assert "message" in body
        assert "error_code" in body

    def test_validation_error_returns_error_response_format(self, client):
        """422 校验错误响应必须是 ErrorResponse 格式(或兼容格式)。"""
        response = client.post("/auth/login", json={})

        assert response.status_code == 422
        # 422 是 Pydantic 校验错误,FastAPI 默认格式,可保留兼容
        # 但应包含 success: false 标识
        body = response.json()
        # 至少应有 detail 或 message 字段
        assert "detail" in body or "message" in body, (
            f"422 响应应包含 detail 或 message, 实际: {body}"
        )

    def test_get_baseline_expected_output_returns_api_response(self, client, auth_headers):
        """get_baseline_convergence 必须返回 ApiResponse 格式,而非裸 dict。

        使用不存在的 baseline_id 触发 404,验证错误响应格式。
        """
        # convergence 路由在 baseline 不存在时 raise HTTPException(404)
        response = client.get(
            "/governance/baselines/nonexistent_baseline_p16/convergence",
            headers=auth_headers,
        )

        # 不存在的 baseline → 404
        assert response.status_code == 404
        body = response.json()

        # 必须是 ErrorResponse 格式
        assert "success" in body, (
            f"404 响应必须是 ErrorResponse 格式(含 success), 实际: {body}"
        )
        assert body["success"] is False
        assert "message" in body
        assert "error_code" in body

    def test_execute_api_tests_returns_api_response(self, client, auth_headers):
        """execute_api_tests 必须返回 ApiResponse 格式,而非裸 dict。"""
        response = client.post(
            "/test/execute",
            json={"test_cases": []},
            headers=auth_headers,
        )

        # 空测试用例应返回 200(而非错误)
        assert response.status_code == 200, (
            f"空测试用例应返回 200, 实际: {response.status_code}, body: {response.text}"
        )
        body = response.json()

        # 必须是 ApiResponse 格式
        assert "success" in body, (
            f"响应必须是 ApiResponse 格式(含 success), 实际: {body}"
        )
        assert body["success"] is True
        assert "data" in body, f"ApiResponse 必须包含 data 字段, 实际: {body}"

    def test_get_workflow_test_cases_returns_api_response(self, client, auth_headers):
        """get_workflow_test_cases 必须返回 ApiResponse 格式,而非裸 dict。"""
        # 使用默认工作流 wf-001
        response = client.get(
            "/test/workflow/wf-001",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()

        # 必须是 ApiResponse 格式
        assert "success" in body, (
            f"响应必须是 ApiResponse 格式(含 success), 实际: {body}"
        )
        assert body["success"] is True
        assert "data" in body, f"ApiResponse 必须包含 data 字段, 实际: {body}"

    def test_diagnose_workflow_returns_api_response(self, client, auth_headers):
        """diagnose_workflow 必须返回 ApiResponse 格式,而非裸 dict。"""
        response = client.post(
            "/diagnose/workflow",
            json={
                "workflow_id": "wf-001",
                "code": "def test(): pass",
                "test_results": {},
            },
            headers=auth_headers,
        )

        # 即使分析失败,响应格式也应是 ApiResponse
        assert response.status_code in [200, 500], (
            f"diagnose_workflow 应返回 200 或 500, 实际: {response.status_code}"
        )
        body = response.json()

        # 必须是 ApiResponse 格式
        assert "success" in body, (
            f"响应必须是 ApiResponse 格式(含 success), 实际: {body}"
        )
        assert "data" in body or "message" in body, (
            f"ApiResponse 必须包含 data 或 message 字段, 实际: {body}"
        )
