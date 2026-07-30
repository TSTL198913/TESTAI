"""BUG-005: acknowledge_alert 对不存在的 alert 返回 200 + success=True。

源码位置:src/platform/api.py:341-351 acknowledge_alert

根因:
- L346 `result = alert_manager.acknowledge_alert(alert_id)` 返回 bool
- L347-351 不管 result True/False 都返回 success=True, message="Alert acknowledged"
- 不存在的 alert 返回 200 + success=True + acknowledged=False,HTTP 语义错误

正确行为:不存在的 alert 应返回 404 + success=False + error_code。

现有测试反模式:tests/platform/test_api.py:198-204
- mock_ack.return_value = True 只测 happy path
- 没测 alert 不存在的场景
"""
import pytest


def test_acknowledge_nonexistent_alert_returns_404(client, admin_headers):
    """不存在的 alert 应返回 404。"""
    response = client.post(
        "/monitoring/alerts/nonexistent-alert-id-12345/acknowledge",
        headers=admin_headers,
    )

    assert response.status_code == 404, (
        f"不存在的 alert 应返回 404,实际: {response.status_code}, "
        f"body: {response.text}"
    )
    data = response.json()
    assert data["success"] is False, (
        f"success 必须为 False,实际: {data.get('success')}"
    )
    assert data.get("error_code") is not None, (
        f"必须包含 error_code 字段,实际: {data}"
    )


def test_acknowledge_nonexistent_alert_message_not_misleading(client, admin_headers):
    """不存在的 alert 的 message 不应误导用户说"Alert acknowledged"。"""
    response = client.post(
        "/monitoring/alerts/another-nonexistent-alert-67890/acknowledge",
        headers=admin_headers,
    )

    data = response.json()
    message = data.get("message", "").lower()
    assert "acknowledged" not in message or "not" in message, (
        f"message 不应误导用户说 'Alert acknowledged',实际: {data.get('message')!r}"
    )


def test_acknowledge_nonexistent_alert_data_acknowledged_false(client, admin_headers):
    """不存在的 alert 应返回 404。"""
    response = client.post(
        "/monitoring/alerts/yet-another-nonexistent-alert/acknowledge",
        headers=admin_headers,
    )

    assert response.status_code == 404, (
        f"应返回 404,实际: {response.status_code}"
    )
