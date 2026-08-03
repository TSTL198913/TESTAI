import pytest
import requests
import json
import os
import uuid

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000")
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


class TestFullStackIntegration:
    """全栈前后端集成测试 - 验证前后端交互正确性"""

    # P0 修复 (429 碰撞隔离):
    #   旧版此处定义 class 级 auth_tokens fixture, 每个测试类独立登录 admin。
    #   全量顺序运行时 admin 登录次数累计触发 5次/60秒 限流 → 后续测试 429 失败。
    #   现改用 tests/integration/conftest.py 的 session 级 auth_tokens fixture,
    #   全 session 只登录 1 次。详见 conftest.py:_session_login 文档。

    def test_health_check(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert data["data"]["status"] == "healthy"
        assert "platform" in data["data"]
        assert data["data"]["platform"] == "TestAI"

    def test_login_api(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "password"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert "user" in data["data"]
        assert data["data"]["user"]["username"] == "admin"
        assert data["data"]["user"]["role"] == "admin"

    def test_login_invalid_credentials(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 401

    def test_refresh_token(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/auth/refresh",
            headers={"Authorization": f"Bearer {auth_tokens['refresh_token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    def test_get_current_user(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/auth/me",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["username"] == "admin"
        assert data["data"]["role"] == "admin"
        assert "permissions" in data["data"]
        assert isinstance(data["data"]["permissions"], list)

    def test_workflow_crud_flow(self, auth_tokens):
        """工作流 CRUD 闭环: define(含 tasks) → list → execute → status。

        旧版假绿/缺陷: define 未传 tasks → 400, 但断言 200 (被 skip 掩盖)。
        源码契约: workflow define 要求 >=1 任务 (否则 "工作流必须包含至少一个任务")。
        """
        workflow_name = f"集成测试工作流_{str(uuid.uuid4())[:8]}"

        # ---- define: 必须含 >=1 任务 ----
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={
                "name": workflow_name,
                "description": "集成测试",
                "tasks": [
                    {"type": "monitoring", "name": "检查状态", "params": {"action": "get_status"}}
                ],
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200, (
            f"workflow define 应 200, 实际: {response.status_code}, body: {response.text}"
        )
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "defined", (
            f"新建工作流 status 应为 'defined', 实际: {data['data'].get('status')}"
        )
        workflow_id = data["data"]["workflow_id"]

        # ---- list ----
        response = requests.get(f"{API_BASE}/workflow", headers=auth_tokens["auth_headers"])
        assert response.status_code == 200
        list_body = response.json()
        assert list_body["success"] is True

        # ---- execute ----
        response = requests.post(
            f"{API_BASE}/workflow/{workflow_id}/execute",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        exec_data = response.json()

        if exec_data.get("success"):
            instance_id = exec_data["data"].get("instance_id", workflow_id)
            response = requests.get(
                f"{API_BASE}/workflow/{instance_id}/status",
                headers=auth_tokens["auth_headers"]
            )
            assert response.status_code in [200, 404]
        else:
            assert "message" in exec_data

    def test_governance_flow(self, auth_tokens):
        """治理流: /governance/execute → /governance/approvals 契约校验。

        旧版仅断言 status_code==200, 不校验 data.trace_id / data.status /
        count==len(approvals), 无法发现治理流返回空数据或字段错位。
        """
        # ---- /governance/execute 契约 (api.py:703-725): data={trace_id, **result} ----
        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={
                "component_name": "test_component",
                "step_id": "test_step",
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        gdata = body["data"]
        # trace_id 必须回显 step_id (api.py:712: trace_id = step_id or uuid)
        assert gdata["trace_id"] == "test_step", (
            f"trace_id 应回显 step_id, 实际: {gdata.get('trace_id')!r}"
        )
        # status 必须是有效治理状态
        valid_statuses = {"FIXED", "SKIPPED", "PENDING_APPROVAL", "FAILED", "DIAGNOSED"}
        assert gdata["status"] in valid_statuses, (
            f"status 必须是有效值 {valid_statuses}, 实际: {gdata.get('status')!r}"
        )
        # 无异常的 test_component → 分类 Non-governable → SKIPPED (确定性, 不调 LLM)
        assert gdata["status"] == "SKIPPED", (
            f"无异常 test_component 应 SKIPPED (Non-governable), 实际: {gdata['status']}"
        )
        assert gdata["confidence_score"] == 0.0

        # ---- /governance/approvals 契约 (api.py:728-741) ----
        response = requests.get(
            f"{API_BASE}/governance/approvals",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "approvals" in data["data"]
        # 一致性: count == len(approvals) (反 tautology)
        assert data["data"]["count"] == len(data["data"]["approvals"]), (
            f"count({data['data']['count']}) 必须等于 len(approvals)"
            f"({len(data['data']['approvals'])})"
        )
        assert isinstance(data["data"]["count"], int)
        # 每个审批项结构完整 (approval.py:45-46 to_dict)
        required_approval_fields = {
            "tx_id", "status", "patch_type", "created_at",
            "approved_by", "approved_at", "reason", "is_expired",
        }
        for apv in data["data"]["approvals"]:
            missing = required_approval_fields - set(apv.keys())
            assert not missing, f"审批记录缺字段: {missing}"

    def test_monitoring_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/monitoring/alerts",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/monitoring/metrics",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_config_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/config",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_dashboard_api(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/dashboard/summary",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.get(
            f"{API_BASE}/dashboard/quality-trend",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_user_management_api(self, auth_tokens):
        new_user = {
            "username": f"testuser_{str(uuid.uuid4())[:8]}",
            "email": f"test_{str(uuid.uuid4())[:8]}@testai.com",
            "role": "viewer"
        }
        
        response = requests.post(
            f"{API_BASE}/users",
            json=new_user,
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "user_id" in data["data"]
        user_id = data["data"]["user_id"]

        response = requests.get(
            f"{API_BASE}/users/{user_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["user_id"] == user_id

        response = requests.put(
            f"{API_BASE}/users/{user_id}",
            json={"role": "tester"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.delete(
            f"{API_BASE}/users/{user_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_team_management_api(self, auth_tokens):
        team_name = f"测试团队_{str(uuid.uuid4())[:8]}"
        
        response = requests.post(
            f"{API_BASE}/teams",
            json={"name": team_name, "description": "测试团队"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "team_id" in data["data"]
        team_id = data["data"]["team_id"]

        response = requests.get(
            f"{API_BASE}/teams/{team_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

        response = requests.delete(
            f"{API_BASE}/teams/{team_id}",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_test_execution_api(self, auth_tokens):
        """/test/execute 契约 (api.py:1511-1572): 本地 URL + 一致性校验。

        旧版假绿: 用例 url=https://api.example.com/test (外部 URL), 无外网环境挂起 timeout。
        runner 目标硬编码 http://localhost:8000, 应用本地相对 URL (/health) 保证确定性。
        """
        test_cases = [{
            "name": "测试用例1",
            "protocol": "http",
            "method": "GET",
            "url": "/health",
            "headers": {"Content-Type": "application/json"},
        }]

        response = requests.post(
            f"{API_BASE}/test/execute",
            json={"test_cases": test_cases},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        # ---- 一致性: passed+failed=total ----
        assert data["total_tests"] == 1
        assert data["passed_tests"] + data["failed_tests"] == data["total_tests"], (
            f"一致性失败: {data['passed_tests']}+{data['failed_tests']}!={data['total_tests']}"
        )
        # /health 在 server live 时应通过
        assert data["passed_tests"] == 1, (
            f"/health 应通过, passed_tests={data['passed_tests']}, "
            f"results={[(r['test_case_name'], r['passed']) for r in data['results']]}"
        )
        assert data["pass_rate"] == 100.0
        # result 真实 passed 值
        r = data["results"][0]
        assert r["passed"] is True
        assert r["status_code"] == 200

    def test_diagnose_api(self, auth_tokens):
        """/diagnose/workflow 契约 (api.py:1671-1727): data={workflow_id, issues, insights, confidence}。"""
        response = requests.post(
            f"{API_BASE}/diagnose/workflow",
            json={"workflow_id": "test_workflow"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["workflow_id"] == "test_workflow", (
            f"workflow_id 应回显请求值, 实际: {data.get('workflow_id')!r}"
        )
        assert isinstance(data["issues"], list)
        assert isinstance(data["insights"], list)
        assert data["confidence"] == 0.85, (
            f"confidence 应为 0.85 (api.py:1723), 实际: {data.get('confidence')}"
        )

    def test_rate_limiting(self):
        """限流契约 (auth.py:221-237): per-username 5次/60秒 → 429 + X-RateLimit-Limit header。

        P0 修复 (429 碰撞隔离):
          旧版用 username="admin" 触发 429, 会污染 admin 的登录计数, 锁定 admin 60 秒,
          导致后续所有依赖 admin 的测试 429 失败。
          限流是 per-username (auth.py:224 _login_attempts.get(username)),
          改用独立用户名 'rate_limit_isolated_user' 触发 429, 不污染 admin。
        """
        isolated_user = "rate_limit_isolated_user"
        for _ in range(10):
            requests.post(
                f"{API_BASE}/auth/login",
                json={"username": isolated_user, "password": "wrong"}
            )

        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": isolated_user, "password": "wrong"}
        )
        assert response.status_code == 429, (
            f"独立用户 {isolated_user} 触发 10+1 次后应 429, 实际: {response.status_code}"
        )
        assert "X-RateLimit-Limit" in response.headers

    def test_unauthorized_access(self):
        response = requests.get(f"{API_BASE}/workflow")
        assert response.status_code == 401

        response = requests.get(f"{API_BASE}/governance/approvals")
        assert response.status_code == 401

    def test_permission_denied(self):
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "viewer", "password": "password"}
        )
        assert response.status_code == 200
        viewer_token = response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {viewer_token}"}

        response = requests.post(
            f"{API_BASE}/governance/approvals/test/approve",
            params={"approver": "viewer"},
            headers=headers
        )
        assert response.status_code == 403

    def test_cors_headers(self):
        """CORS 契约 (api.py:103-120, 153-159)。

        旧版假绿: 用 Origin=http://localhost:3001, 但该源不在 dev 默认白名单
        [localhost:3000, localhost:8080, 127.0.0.1:3000] → 服务器不返回
        access-control-allow-origin, 旧版断言必失败 (被 skip 掩盖)。
        修复: 正向用白名单内源 (3000), 负向用白名单外源 (3001) 双向校验。
        """
        # ---- 正向: 白名单内源 → 应返回 allow-origin ----
        response = requests.get(f"{API_BASE}/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers_lower, (
            "白名单内源 (localhost:3000) 应触发 access-control-allow-origin"
        )
        assert headers_lower["access-control-allow-origin"] == "http://localhost:3000", (
            f"allow-origin 应回显源, 实际: {headers_lower.get('access-control-allow-origin')!r}"
        )
        assert "access-control-allow-credentials" in headers_lower

        # ---- 负向: 白名单外源 → 不应返回 allow-origin ----
        response = requests.get(f"{API_BASE}/health", headers={"Origin": "http://localhost:3001"})
        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" not in headers_lower, (
            "白名单外源 (localhost:3001) 不应返回 access-control-allow-origin — "
            "若返回说明 CORS 白名单失效 (过度开放)"
        )

    def test_api_response_format(self, auth_tokens):
        endpoints = [
            f"{API_BASE}/workflow",
            f"{API_BASE}/monitoring/alerts",
            f"{API_BASE}/dashboard/summary",
        ]
        
        for endpoint in endpoints:
            response = requests.get(endpoint, headers=auth_tokens["auth_headers"])
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)

    def test_full_workflow_to_governance_flow(self, auth_tokens):
        """全流程: workflow define → execute → governance execute → approvals。

        旧版 3 处假绿/缺陷:
          1. workflow define 未传 tasks → 400 (源码要求 >=1 任务), 旧版断言 200 必失败
             (被 skip 掩盖)。
          2. governance execute 仅断言 status==200, 不校验 trace_id/status。
          3. approvals 仅断言 status==200, 不校验 count==len(approvals)。
        """
        workflow_name = f"全流程测试_{str(uuid.uuid4())[:8]}"

        # ---- workflow define: 必须含 >=1 任务 (否则 400) ----
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={
                "name": workflow_name,
                "description": "全流程测试",
                "tasks": [
                    {"type": "monitoring", "name": "检查状态", "params": {"action": "get_status"}}
                ],
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200, (
            f"workflow define 应 200, 实际: {response.status_code}, body: {response.text}"
        )
        wf_body = response.json()
        assert wf_body["success"] is True
        assert wf_body["data"]["status"] == "defined", (
            f"新建工作流 status 应为 'defined', 实际: {wf_body['data'].get('status')}"
        )
        workflow_id = wf_body["data"]["workflow_id"]

        # ---- workflow execute ----
        response = requests.post(
            f"{API_BASE}/workflow/{workflow_id}/execute",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        exec_data = response.json()

        if exec_data.get("success"):
            instance_id = exec_data["data"].get("instance_id", workflow_id)
            response = requests.get(
                f"{API_BASE}/workflow/{instance_id}/status",
                headers=auth_tokens["auth_headers"]
            )
            assert response.status_code in [200, 404]

        # ---- governance execute 契约 (无 step_id → trace_id=uuid) ----
        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={"component_name": workflow_name},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        g_body = response.json()
        assert g_body["success"] is True
        gdata = g_body["data"]
        # 无 step_id → trace_id 自动生成 (uuid[:8], 非空字符串)
        assert isinstance(gdata["trace_id"], str) and len(gdata["trace_id"]) > 0, (
            f"无 step_id 时 trace_id 应自动生成, 实际: {gdata.get('trace_id')!r}"
        )
        valid_statuses = {"FIXED", "SKIPPED", "PENDING_APPROVAL", "FAILED", "DIAGNOSED"}
        assert gdata["status"] in valid_statuses, (
            f"status 必须是有效值, 实际: {gdata.get('status')!r}"
        )

        # ---- approvals 契约 + 一致性 ----
        response = requests.get(
            f"{API_BASE}/governance/approvals",
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        a_body = response.json()
        assert a_body["success"] is True
        assert a_body["data"]["count"] == len(a_body["data"]["approvals"]), (
            f"count({a_body['data']['count']}) 必须等于 len(approvals)"
            f"({len(a_body['data']['approvals'])})"
        )

    def test_health_check_endpoint_structure(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert "platform" in data["data"]
        assert "version" in data["data"]
        assert "governance_status" in data["data"]

    def test_version_endpoint(self):
        response = requests.get(f"{API_BASE}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "version" in data["data"]

    def test_user_list_pagination(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/users",
            params={"page": 1, "limit": 5},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "count" in data["data"]
        assert "users" in data["data"]
        assert isinstance(data["data"]["users"], list)

    def test_workflow_list_with_filter(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/workflow",
            params={"name": "Test"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200

    def test_governance_execute_with_params(self, auth_tokens):
        """治理执行 + force 参数契约校验。

        暴露的契约缺口: endpoint (api.py:703-711) 签名仅含 component_name/step_id/
        input_data/actual_output/expected_baseline, 无 force 参数 —— FastAPI 静默忽略
        未知 query 参数, 故 force=true 实际不生效。旧版仅断言 status==200, 掩盖此缺口。
        """
        response = requests.post(
            f"{API_BASE}/governance/execute",
            params={
                "component_name": "test_component",
                "step_id": "test_step",
                "force": "true"
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        gdata = body["data"]
        # trace_id 回显 step_id (与无 force 时一致 —— force 未实现)
        assert gdata["trace_id"] == "test_step", (
            f"trace_id 应回显 step_id, 实际: {gdata.get('trace_id')!r}"
        )
        valid_statuses = {"FIXED", "SKIPPED", "PENDING_APPROVAL", "FAILED", "DIAGNOSED"}
        assert gdata["status"] in valid_statuses, (
            f"status 必须是有效值, 实际: {gdata.get('status')!r}"
        )
        # force 未实现 → 行为与无 force 一致 (SKIPPED)
        assert gdata["status"] == "SKIPPED", (
            f"force 未实现, 应与无 force 一致 (SKIPPED), 实际: {gdata['status']} — "
            "若 status 变化说明 force 被悄悄实现了, 需更新契约文档"
        )

    def test_monitoring_alerts_with_filter(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/monitoring/alerts",
            params={"level": "ERROR"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_dashboard_quality_trend(self, auth_tokens):
        response = requests.get(
            f"{API_BASE}/dashboard/quality-trend",
            params={"days": 7},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_config_section_access(self, auth_tokens):
        """配置 section 访问契约 (api.py:942-957)。

        旧版 2 处假绿:
          1. 顶层断言 "name" in data —— P1-6 后字段在 data["data"] 下 (stale nesting)。
          2. 用 section=platform —— live server 仅加载 "api" section, platform 返回 None,
             旧版断言必失败 (被 skip 掩盖)。
        暴露的配置缺口: live server config_manager 仅含 "api" section,
        缺 platform/workflow/governance 等默认 section (与 test_config_manager 单测的默认值不一致)。
        """
        # ---- 正向: section=api (live server 实际加载的 section) ----
        response = requests.get(
            f"{API_BASE}/config",
            params={"section": "api"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        cfg = body["data"]
        assert cfg is not None, f"section=api 应返回非 None 配置, 实际: {cfg}"
        assert cfg["name"] == "api", (
            f"section=api 的 name 应为 'api', 实际: {cfg.get('name')!r}"
        )
        assert "port" in cfg, f"section=api 应含 port 字段, 实际: {list(cfg.keys())}"

        # ---- 边界: 不存在的 section → data=None (优雅降级, 不 500) ----
        response = requests.get(
            f"{API_BASE}/config",
            params={"section": "nonexistent_section_xyz"},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        none_body = response.json()
        assert none_body["success"] is True
        assert none_body["data"] is None, (
            f"不存在的 section 应返回 data=None, 实际: {none_body['data']!r}"
        )

    def test_create_workflow_with_tasks(self, auth_tokens):
        workflow_name = f"带任务工作流_{str(uuid.uuid4())[:8]}"
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={
                "name": workflow_name,
                "description": "带任务的工作流",
                "tasks": [
                    {"type": "monitoring", "name": "检查状态", "params": {"action": "get_status"}}
                ]
            },
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "workflow_id" in data["data"]

    def test_empty_request_body(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/workflow/define",
            json={},
            headers=auth_tokens["auth_headers"]
        )
        assert response.status_code == 422

    def test_invalid_json_format(self, auth_tokens):
        response = requests.post(
            f"{API_BASE}/auth/login",
            data="not valid json",
            headers={"Content-Type": "application/json", **auth_tokens["auth_headers"]}
        )
        assert response.status_code == 422

    def test_rate_limit_response_headers(self):
        for _ in range(5):
            requests.post(
                f"{API_BASE}/auth/login",
                json={"username": "admin", "password": "wrong"}
            )
        
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": "admin", "password": "wrong"}
        )
        if response.status_code == 429:
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers

    def test_cors_preflight_request(self):
        response = requests.options(
            f"{API_BASE}/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers_lower
        assert "access-control-allow-methods" in headers_lower
        assert "access-control-allow-headers" in headers_lower