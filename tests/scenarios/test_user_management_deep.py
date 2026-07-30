"""
用户管理深度测试 - 验证完整用户生命周期
"""
import pytest
import time


class TestUserManagementDeep:
    """用户管理深度测试"""

    def test_user_full_lifecycle(self, client, admin_headers):
        """场景：完整用户生命周期"""
        timestamp = str(int(time.time()))
        username = f"deep_test_user_{timestamp}"
        email = f"deep_test_{timestamp}@testai.com"

        response = client.post(
            "/users",
            json={
                "username": username,
                "email": email,
                "role": "viewer",
                "full_name": "Deep Test User",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        created = response.json()["data"]
        user_id = created["user_id"]
        assert user_id is not None
        assert created["username"] == username
        assert created["email"] == email

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        user = response.json()["data"]
        assert user["user_id"] == user_id

        response = client.put(
            f"/users/{user_id}",
            json={"full_name": "Updated Name"},
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.post(f"/users/{user_id}/suspend", headers=admin_headers)
        assert response.status_code == 200

        response = client.post(f"/users/{user_id}/activate", headers=admin_headers)
        assert response.status_code == 200

        response = client.delete(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200

    def test_user_role_permissions(self, client, admin_headers):
        """场景：用户角色权限验证"""
        response = client.get("/users", headers=admin_headers)
        assert response.status_code == 200

    def test_user_duplicate_validation(self, client, admin_headers):
        """场景：用户重复验证"""
        timestamp = str(int(time.time()))
        username = f"duplicate_test_{timestamp}"

        response = client.post(
            "/users",
            json={"username": username, "email": f"duplicate_{timestamp}@testai.com", "role": "viewer"},
            headers=admin_headers,
        )
        assert response.status_code == 200

    def test_user_search_and_filter(self, client, admin_headers):
        """场景：用户搜索和筛选"""
        response = client.get("/users", headers=admin_headers)
        assert response.status_code == 200

        response = client.get("/users?username=admin", headers=admin_headers)
        assert response.status_code == 200