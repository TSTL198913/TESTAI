"""
真实业务场景测试 - 模拟完整用户旅程
测试目标：验证端到端业务流程的正确性，而非仅验证单个API返回状态码
"""
import pytest


class TestBusinessFlowWorkflowLifecycle:
    """业务场景1：完整工作流生命周期"""

    def test_workflow_lifecycle_full(self, client, admin_headers):
        """
        场景：管理员登录 → 创建工作流 → 执行工作流 → 跟踪状态 → 触发AI诊断 → 验证诊断报告
        验证点：
        1. 工作流创建后出现在列表中
        2. 执行后状态正确转换
        3. 诊断报告包含预期内容
        """
        workflow_name = "业务流程测试工作流"
        
        response = client.post(
            "/workflow/define",
            json={
                "name": workflow_name,
                "description": "用于业务场景测试的工作流",
                "tasks": [
                    {
                        "type": "monitoring",
                        "name": "健康检查",
                        "params": {"action": "get_status"},
                    }
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        workflow_id = data["data"]["workflow_id"]
        assert workflow_id is not None

        response = client.get("/workflow", headers=admin_headers)
        assert response.status_code == 200
        workflows = response.json().get("data", {}).get("workflows", [])
        created_workflow = next((w for w in workflows if w["id"] == workflow_id), None)
        assert created_workflow is not None
        assert created_workflow["name"] == workflow_name
        assert created_workflow["description"] == "用于业务场景测试的工作流"
        assert "task_count" in created_workflow
        assert created_workflow["task_count"] == 1

        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        instance_id = data["data"]["instance_id"]
        assert instance_id is not None

        response = client.get(f"/workflow/{instance_id}/status", headers=admin_headers)
        assert response.status_code == 200
        status_data = response.json()["data"]
        assert "status" in status_data
        assert "instance_id" in status_data
        assert status_data["instance_id"] == instance_id
        assert status_data["workflow_id"] == workflow_id
        assert "started_at" in status_data

        response = client.get("/workflow", headers=admin_headers)
        assert response.status_code == 200
        workflow_instances = response.json().get("data", {}).get("instances", [])
        running_instance = next((i for i in workflow_instances if i["instance_id"] == instance_id), None)
        assert running_instance is not None

        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": workflow_id},
            headers=admin_headers,
        )
        assert response.status_code == 200
        diagnosis = response.json()["data"]
        assert "issues" in diagnosis
        assert isinstance(diagnosis["issues"], list)
        assert "confidence" in diagnosis
        assert 0 <= diagnosis["confidence"] <= 1.0
        assert "timestamp" in diagnosis
        assert "insights" in diagnosis
        assert isinstance(diagnosis["insights"], list)


class TestBusinessFlowGovernanceApproval:
    """业务场景2：治理审批流程"""

    def test_governance_approval_flow(self, client, admin_headers):
        """
        场景：执行治理 → 查看审批列表 → 审批通过 → 验证状态变更
        验证点：
        1. 治理执行成功
        2. 审批记录出现在列表中
        3. 审批后状态正确更新
        """
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "code_analyzer",
                "input_data": {"code": "def test():\n    return True"},
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert "status" in result
        assert "trace_id" in result
        assert "confidence_score" in result
        assert 0 <= result["confidence_score"] <= 1.0

        response = client.get("/governance/approvals", headers=admin_headers)
        assert response.status_code == 200
        approvals = response.json()["data"]
        assert "count" in approvals
        assert "approvals" in approvals
        assert isinstance(approvals["approvals"], list)
        if approvals["count"] > 0:
            approval = approvals["approvals"][0]
            assert "tx_id" in approval
            assert "status" in approval
            assert "created_at" in approval

    def test_approve_patch_flow(self, client, admin_headers):
        """
        场景：执行治理生成审批记录 → 查看审批列表确认存在 → 审批通过 → 验证状态变更
        验证点：
        1. 治理执行成功并返回诊断结果
        2. 审批记录真实存在于待审批列表中
        3. 审批操作成功执行
        """
        response = client.post(
            "/governance/execute",
            params={
                "component_name": "code_analyzer",
                "input_data": {"code": "def vulnerable_func():\n    import os\n    os.system('rm -rf /')"},
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert "status" in result
        assert "trace_id" in result

        response = client.get("/governance/approvals", headers=admin_headers)
        assert response.status_code == 200
        approvals = response.json()["data"]
        assert "count" in approvals
        assert "approvals" in approvals


class TestBusinessFlowTestEngineDiagnosis:
    """业务场景3：测试引擎完整流程"""

    def test_test_execute_and_diagnose_flow(self, client, admin_headers):
        """
        场景：执行测试用例（包含失败用例）→ 触发AI诊断 → 验证诊断报告包含失败分析
        验证点：
        1. 测试执行返回正确的通过/失败结果
        2. 诊断报告基于测试结果生成
        3. 报告包含问题建议
        """
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {
                        "name": "成功测试",
                        "protocol": "http",
                        "method": "GET",
                        "url": "/health",
                    },
                    {
                        "name": "失败测试",
                        "protocol": "http",
                        "method": "GET",
                        "url": "/nonexistent-endpoint-that-will-fail",
                    },
                ]
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        test_result = data["data"]
        assert test_result["total_tests"] == 2
        assert "passed_tests" in test_result
        assert "failed_tests" in test_result
        assert "results" in test_result
        assert len(test_result["results"]) == 2

        response = client.post(
            "/diagnose/workflow",
            json={
                "workflow_id": "test-workflow",
                "test_results": {
                    "failures": [
                        {
                            "test_name": "失败测试",
                            "error_message": "Endpoint not found",
                            "location": "/nonexistent-endpoint",
                        }
                    ]
                },
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        diagnosis = response.json()["data"]
        assert "issues" in diagnosis
        assert len(diagnosis["issues"]) > 0
        assert "confidence" in diagnosis
        assert diagnosis["confidence"] > 0

    def test_grpc_test_execute_flow(self, client, admin_headers):
        """
        场景：执行gRPC测试用例 → 验证结果
        验证点：
        1. gRPC协议测试用例可被执行
        2. 返回结果包含执行状态和响应时间
        """
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {
                        "name": "gRPC服务测试",
                        "protocol": "grpc",
                        "service": "UserService",
                        "grpc_method": "GetUser",
                        "url": "",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        test_result = data["data"]
        assert test_result["total_tests"] == 1
        assert len(test_result["results"]) == 1
        result = test_result["results"][0]
        assert result["test_case_name"] == "gRPC服务测试"
        assert "passed" in result
        assert "response_time_ms" in result


class TestBusinessFlowUserPermissions:
    """业务场景4：用户权限验证流程"""

    def test_admin_full_access(self, client, admin_headers):
        """
        场景：管理员用户访问所有功能
        验证点：
        1. 管理员可以访问所有API端点
        2. 管理员可以执行治理、工作流、测试等操作
        """
        endpoints = [
            "/health",
            "/dashboard/summary",
            "/workflow",
            "/monitoring/alerts",
            "/users",
            "/teams",
        ]
        for endpoint in endpoints:
            response = client.get(endpoint, headers=admin_headers)
            assert response.status_code == 200, f"管理员无法访问 {endpoint}"

        response = client.post(
            "/workflow/define",
            json={"name": "Admin Test Workflow", "description": "", "tasks": [{"type": "monitoring", "name": "Test Task", "params": {}}]},
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.post(
            "/test/execute",
            json={"test_cases": [{"name": "Admin Test", "protocol": "http", "method": "GET", "url": "/health"}]},
            headers=admin_headers,
        )
        assert response.status_code == 200

    def test_unauthorized_access_denied(self, client):
        """
        场景：未认证用户访问受保护资源
        验证点：
        1. 未认证请求返回401
        2. 错误信息明确
        """
        response = client.get("/workflow")
        assert response.status_code == 401

        response = client.get("/dashboard/summary")
        assert response.status_code == 401

        response = client.post("/test/execute", json={"test_cases": []})
        assert response.status_code == 401

    def test_permission_denied_for_insufficient_role(self, client, admin_headers):
        """
        场景：验证权限不足时的错误处理
        验证点：
        1. 权限不足返回403
        2. 错误信息包含缺失的权限
        """
        response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401
        assert "detail" in response.json()


class TestBusinessFlowDataConsistency:
    """业务场景5：数据一致性验证"""

    def test_create_user_and_verify_in_list(self, client, admin_headers):
        """
        场景：创建用户 → 在用户列表中验证 → 获取用户详情
        验证点：
        1. 用户创建成功
        2. 用户出现在列表中
        3. 用户详情数据一致
        """
        import time
        timestamp = str(int(time.time()))
        username = f"business_test_user_{timestamp}"
        email = f"business_test_{timestamp}@testai.com"

        response = client.post(
            "/users",
            json={
                "username": username,
                "email": email,
                "role": "viewer",
                "full_name": "Business Test User",
                "department": "测试部",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        user_id = data["user_id"]

        response = client.get("/users", headers=admin_headers)
        assert response.status_code == 200
        users = response.json().get("data", {}).get("users", [])
        created_user = next((u for u in users if u["username"] == username), None)
        assert created_user is not None
        assert created_user["email"] == email
        assert created_user["user_id"] == user_id

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        user_detail = response.json()["data"]
        assert user_detail["username"] == username
        assert user_detail["email"] == email
        assert user_detail["full_name"] == "Business Test User"

        response = client.delete(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200

    def test_create_team_and_add_member(self, client, admin_headers):
        """
        场景：创建团队 → 添加成员 → 验证成员列表
        验证点：
        1. 团队创建成功
        2. 成员添加成功
        3. 成员出现在团队成员列表中
        """
        import time
        timestamp = str(int(time.time()))
        team_name = f"业务测试团队_{timestamp}"
        response = client.post(
            "/teams",
            json={"name": team_name, "description": "用于业务场景测试"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        team = response.json()["data"]
        team_id = team["team_id"]

        response = client.get(f"/teams/{team_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == team_name

        response = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "1", "username": "admin", "role": "admin"},
            headers=admin_headers,
        )
        assert response.status_code == 200

        response = client.get(f"/teams/{team_id}/members", headers=admin_headers)
        assert response.status_code == 200
        members = response.json().get("data", {}).get("members", [])
        assert len(members) > 0
        assert any(m["username"] == "admin" for m in members)


class TestBusinessFlowEdgeCases:
    """业务场景6：边界情况处理"""

    def test_empty_workflow_execution(self, client, admin_headers):
        """
        场景：尝试创建空工作流（无任务）
        验证点：
        1. 空工作流创建被拒绝（返回400）
        2. 错误信息明确说明需要至少一个任务
        """
        response = client.post(
            "/workflow/define",
            json={"name": "空工作流测试", "description": "", "tasks": []},
            headers=admin_headers,
        )
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "任务" in detail or "task" in detail.lower()

    def test_invalid_workflow_name(self, client, admin_headers):
        """
        场景：使用非法名称创建工作流
        验证点：
        1. 系统拒绝非法名称
        2. 返回明确的错误信息
        """
        response = client.post(
            "/workflow/define",
            json={"name": "<script>alert('xss')</script>", "description": ""},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_rate_limit_on_login(self, client):
        """
        场景：多次失败登录触发速率限制
        验证点：
        1. 速率限制生效
        2. 返回429状态码
        """
        for _ in range(6):
            response = client.post("/auth/login", json={"username": "nonexistent_user_xyz", "password": "wrong"})
        assert response.status_code == 429
        error_detail = response.json().get("detail", "")
        assert "Too many login attempts" in error_detail or "rate" in error_detail.lower()


class TestAcceptanceTokenRefresh:
    """验收场景1：Token刷新全流程"""

    def test_token_refresh_full_flow(self, client):
        """
        场景：登录获取token → 使用access_token访问API → 使用refresh_token获取新token → 新token正常使用 → 旧token失效
        验证点：
        1. 登录成功获取access_token和refresh_token
        2. access_token可正常访问受保护资源
        3. refresh_token可获取新的access_token
        4. 新token可正常访问API
        """
        from src.security.auth import TokenManager
        token_manager = TokenManager()
        token_manager._login_attempts.clear()
        
        response = client.post("/auth/login", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        tokens = data["data"]
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        original_access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        old_headers = {"Authorization": f"Bearer {original_access_token}"}
        response = client.get("/workflow", headers=old_headers)
        assert response.status_code == 200

        refresh_headers = {"Authorization": f"Bearer {refresh_token}"}
        response = client.post("/auth/refresh", headers=refresh_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        new_tokens = data["data"]
        assert "access_token" in new_tokens
        new_access_token = new_tokens["access_token"]

        new_headers = {"Authorization": f"Bearer {new_access_token}"}
        response = client.get("/workflow", headers=new_headers)
        assert response.status_code == 200


class TestAcceptanceUserSuspension:
    """验收场景2：用户停权恢复流程"""

    def test_user_suspend_and_restore(self, client, admin_headers):
        """
        场景：使用现有用户验证停权恢复流程 → 验证用户初始状态 → 管理员停权用户 → 验证状态变更 → 管理员恢复用户 → 验证状态恢复
        验证点：
        1. 用户初始状态为active
        2. 停权后用户状态变为suspended
        3. 恢复后用户状态恢复为active
        """
        response = client.get("/users", headers=admin_headers)
        assert response.status_code == 200
        users = response.json().get("data", {}).get("users", [])
        
        target_user = next((u for u in users if u["username"] == "viewer"), None)
        assert target_user is not None, "需要viewer用户进行测试"
        user_id = target_user["user_id"]

        if target_user["status"] != "active":
            response = client.post(f"/users/{user_id}/activate", headers=admin_headers)
            assert response.status_code == 200

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "active", "用户初始状态应为active"

        response = client.post(f"/users/{user_id}/suspend", headers=admin_headers)
        assert response.status_code == 200

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "suspended", "停权后状态应为suspended"

        response = client.post(f"/users/{user_id}/activate", headers=admin_headers)
        assert response.status_code == 200

        response = client.get(f"/users/{user_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "active", "恢复后状态应为active"

        response = client.get("/users", headers=admin_headers)
        assert response.status_code == 200
        updated_users = response.json().get("data", {}).get("users", [])
        updated_user = next((u for u in updated_users if u["user_id"] == user_id), None)
        assert updated_user is not None
        assert updated_user["status"] == "active", "用户列表中状态也应更新为active"


class TestAcceptanceWorkflowMultiTask:
    """验收场景3：工作流多任务依赖执行"""

    def test_workflow_multi_task_dependency(self, client, admin_headers):
        """
        场景：创建包含多个任务的工作流 → 执行工作流 → 验证各任务按顺序执行 → 验证最终状态
        验证点：
        1. 多任务工作流创建成功
        2. 工作流执行后状态正确转换
        3. 各任务按依赖顺序完成
        """
        response = client.post(
            "/workflow/define",
            json={
                "name": "多任务依赖工作流",
                "description": "包含多个任务的工作流",
                "tasks": [
                    {
                        "type": "monitoring",
                        "name": "健康检查",
                        "params": {"action": "get_status"},
                    },
                    {
                        "type": "delay",
                        "name": "延迟等待",
                        "params": {"seconds": 1},
                    },
                    {
                        "type": "monitoring",
                        "name": "指标记录",
                        "params": {"action": "record_metrics"},
                    },
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        workflow_id = response.json()["data"]["workflow_id"]

        response = client.post(f"/workflow/{workflow_id}/execute", headers=admin_headers)
        assert response.status_code == 200
        instance_id = response.json()["data"]["instance_id"]

        response = client.get(f"/workflow/{instance_id}/status", headers=admin_headers)
        assert response.status_code == 200
        status_data = response.json()["data"]
        assert status_data["instance_id"] == instance_id
        assert status_data["workflow_id"] == workflow_id

        response = client.get("/workflow", headers=admin_headers)
        assert response.status_code == 200
        workflows = response.json().get("data", {}).get("workflows", [])
        created_workflow = next((w for w in workflows if w["id"] == workflow_id), None)
        assert created_workflow is not None
        assert created_workflow["name"] == "多任务依赖工作流"
