"""测试引擎 + AI 诊断 API 端到端测试。

契约依据 (src/platform/api.py):
  - POST /test/execute  (L1511-1572): ApiResponse(success, data={total_tests,
    passed_tests, failed_tests, pass_rate, results}, message)
    每个 result: {test_case_name, passed, status_code, response_time_ms,
    error_message, assertions}
    pass_rate = passed_tests/total_tests*100 (total=0 时为 0)
    runner 目标硬编码 http://localhost:8000 (故本套件需 live server)
  - POST /test/generate (L1631-1662): ApiResponse(success=result.success,
    data={total_generated, test_cases, error_message, fallback_used})
  - POST /diagnose/workflow (L1671-1727): ApiResponse(success, data={
    workflow_id, issues, insights, confidence, timestamp})

反模式修复 (本文件原为假绿):
  1. 旧版访问 data["total_tests"] 等顶层字段, 但 P1-6 后响应为 ApiResponse
     格式 {success, data:{...}}, 字段在 data["data"] 下 → 11 个测试 KeyError。
  2. 旧版断言 "passed" in result (键存在) 而非 result["passed"] is True,
     掩盖连接失败导致的 passed=False。
  3. 旧版只断言 total_tests == N, 不校验 passed/failed/pass_rate 一致性。
  4. insights 结构校验为空列表时 for 循环不执行 (tautology)。

注: 本套件受 tests/integration/conftest.py 的 require_live_api 守卫保护,
无 live server (localhost:8000) 时整体 skip —— 这是设计意图 (端到端需真实服务)。
"""
import pytest
from unittest.mock import patch, MagicMock


class TestTestEngineAPI:
    """测试引擎API端到端测试"""

    def test_execute_test_cases_http_success(self, client, auth_headers):
        """正向: GET /health (server live) → passed=True + 完整契约 + 一致性。

        server live 时 /health 返回 200, 断言期望 200 → passed=True。
        旧版仅断言 "passed" in result (键存在), 即使连接失败 passed=False 也通过。
        """
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {
                        "name": "健康检查测试",
                        "protocol": "http",
                        "method": "GET",
                        "url": "/health",
                        "headers": {"Content-Type": "application/json"},
                    }
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
        assert "total_tests" in data
        assert "passed_tests" in data
        assert "failed_tests" in data
        assert "pass_rate" in data
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["test_case_name"] == "健康检查测试"
        assert "passed" in data["results"][0]
        assert "status_code" in data["results"][0]
        assert "response_time_ms" in data["results"][0]
=======
        body = response.json()
        # P1-6 契约: 字段在 data 下, 非顶层
        data = body["data"]
        assert data["total_tests"] == 1
        assert data["passed_tests"] == 1, (
            f"/health 在 server live 时应 passed=True, 实际 passed_tests={data['passed_tests']}"
        )
        assert data["failed_tests"] == 0
        assert data["pass_rate"] == 100.0, (
            f"1/1 通过应 pass_rate=100.0, 实际: {data['pass_rate']}"
        )

        # ---- 一致性校验 (反 tautology): passed+failed=total, pass_rate 正确 ----
        assert data["passed_tests"] + data["failed_tests"] == data["total_tests"], (
            "passed_tests + failed_tests 必须等于 total_tests"
        )
        expected_rate = data["passed_tests"] / data["total_tests"] * 100
        assert data["pass_rate"] == expected_rate, (
            f"pass_rate 应为 {expected_rate}, 实际 {data['pass_rate']}"
        )

        # ---- result 结构 + 真实 passed 值 (非键存在) ----
        results = data["results"]
        assert len(results) == 1
        r = results[0]
        assert r["test_case_name"] == "健康检查测试"
        assert r["passed"] is True, (
            f"/health 应 passed=True, 实际 passed={r['passed']}, "
            f"error_message={r.get('error_message')!r}"
        )
        assert r["status_code"] == 200, (
            f"/health 应返回 200, 实际 status_code={r['status_code']}"
        )
        assert isinstance(r["response_time_ms"], (int, float))
        assert r["response_time_ms"] >= 0
        # assertions 列表非空且断言通过
        assert isinstance(r["assertions"], list)
        assert len(r["assertions"]) >= 1, "应至少有 1 个 status_code 断言"
        assert r["assertions"][0]["passed"] is True
        assert r["assertions"][0]["actual"] == 200
        assert r["assertions"][0]["expected"] == 200
>>>>>>> Stashed changes

    def test_execute_test_cases_empty_list(self, client, auth_headers):
        """边界: 空用例列表 → total=0, pass_rate=0 (除零保护)。"""
        response = client.post(
            "/test/execute",
            json={"test_cases": []},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["total_tests"] == 0
        assert data["passed_tests"] == 0
        assert data["failed_tests"] == 0
        # P1-6 契约: total=0 时 pass_rate=0 (api.py:1568 三元保护)
        assert data["pass_rate"] == 0, (
            f"空列表 pass_rate 必须为 0 (除零保护), 实际: {data['pass_rate']}"
        )
        assert data["results"] == []

    def test_execute_test_cases_multiple(self, client, auth_headers):
        """正向: 2 个 /health 用例 → total=2 + 一致性校验。"""
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "测试1", "protocol": "http", "method": "GET", "url": "/health"},
                    {"name": "测试2", "protocol": "http", "method": "GET", "url": "/health"},
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["total_tests"] == 2
        assert len(data["results"]) == 2, (
            f"results 数量必须等于 total_tests, 实际: {len(data['results'])}"
        )
        # ---- 一致性: passed+failed=total ----
        assert data["passed_tests"] + data["failed_tests"] == data["total_tests"], (
            f"一致性失败: {data['passed_tests']}+{data['failed_tests']}!={data['total_tests']}"
        )
        # server live 时两个 /health 都应通过
        assert data["passed_tests"] == 2, (
            f"2 个 /health 应全部通过, 实际 passed={data['passed_tests']}, "
            f"results={[(r['test_case_name'], r['passed']) for r in data['results']]}"
        )
        assert data["pass_rate"] == 100.0
        # result 名称对应
        names = [r["test_case_name"] for r in data["results"]]
        assert names == ["测试1", "测试2"]

    def test_execute_test_cases_unauthorized(self, client):
        """负向: 无认证 → 401。"""
        response = client.post(
            "/test/execute",
            json={"test_cases": [{"name": "测试", "protocol": "http", "method": "GET", "url": "/health"}]},
        )
        assert response.status_code == 401

    def test_execute_test_cases_invalid_url(self, client, auth_headers):
        """负向: 不存在的 URL → passed=False + failed=1 + pass_rate=0。

        无论 server 是否 live, /nonexistent_endpoint 都失败:
          - server up → 404 (断言期望 200 → 失败)
          - server down → 连接错误 (异常兜底 → 失败)
        旧版仅断言 total_tests==1, 不校验失败结果, 掩盖 runner 失败检测失效。
        """
        response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "无效URL测试", "protocol": "http", "method": "GET", "url": "/nonexistent_endpoint"}
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["total_tests"] == 1
        assert data["failed_tests"] == 1, (
            f"无效 URL 应失败, failed_tests 应为 1, 实际: {data['failed_tests']}"
        )
        assert data["passed_tests"] == 0
        assert data["pass_rate"] == 0, (
            f"全部失败 pass_rate 应为 0, 实际: {data['pass_rate']}"
        )
        # ---- result 真实失败状态 ----
        r = data["results"][0]
        assert r["passed"] is False, (
            f"无效 URL 的用例必须 passed=False, 实际: {r['passed']} — "
            "runner 失败检测失效 (断言未正确评估或异常未捕获)"
        )
        assert r["test_case_name"] == "无效URL测试"
        # status_code: server up 时 404, down 时 None — 都 != 200
        assert r["status_code"] != 200, (
            f"无效 URL status_code 不应为 200, 实际: {r['status_code']}"
        )
        # 断言结果记录了失败
        assert isinstance(r["assertions"], list)
        assert len(r["assertions"]) >= 1
        assert r["assertions"][0]["passed"] is False, (
            "status_code 断言应评估为失败"
        )
        assert r["assertions"][0]["expected"] == 200

    def test_generate_test_cases(self, client, auth_headers):
        """正向: 有效 spec → 生成用例 + 结构校验 + total 一致性。"""
        spec = {
            "name": "用户管理API",
            "description": "用户管理相关接口测试",
            "endpoints": [
                {"method": "GET", "path": "/users", "description": "获取用户列表"}
            ],
        }
        response = client.post("/test/generate", json=spec, headers=auth_headers)
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        assert "success" in resp
        data = resp.get("data", resp)
        assert "total_generated" in data
        assert "test_cases" in data
=======
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert isinstance(data["total_generated"], int)
        assert data["total_generated"] >= 0
        assert isinstance(data["test_cases"], list)
        # ---- 一致性: total_generated == len(test_cases) ----
        assert data["total_generated"] == len(data["test_cases"]), (
            f"total_generated({data['total_generated']}) 必须等于 "
            f"len(test_cases)({len(data['test_cases'])})"
        )
        # ---- 每个用例结构完整 (api.py:1644-1654) ----
        required_tc_fields = {"id", "name", "type", "description", "steps",
                              "expected_results", "priority", "tags"}
        for tc in data["test_cases"]:
            missing = required_tc_fields - set(tc.keys())
            assert not missing, f"生成的用例缺字段: {missing}, 实际: {list(tc.keys())}"
        # fallback_used 应为 bool (契约字段)
        assert isinstance(data["fallback_used"], bool)
>>>>>>> Stashed changes

    def test_generate_test_cases_empty_spec(self, client, auth_headers):
        """边界: 空 spec → 仍返回完整契约结构 (不 500)。"""
        response = client.post("/test/generate", json={}, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        # ---- 契约字段必须存在 (非仅 status==200) ----
        assert "success" in body
        data = body["data"]
        assert "total_generated" in data, f"data 缺 total_generated: {data}"
        assert "test_cases" in data
        assert isinstance(data["test_cases"], list)
        assert "fallback_used" in data
        assert "error_message" in data
        # 一致性
        assert data["total_generated"] == len(data["test_cases"])


class TestDiagnoseAPI:
    """AI诊断API端到端测试"""

    def test_diagnose_workflow_empty(self, client, auth_headers):
        """边界: 无 code 无 test_results → issues=[], insights=list, confidence=0.85。"""
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
        assert data["workflow_id"] == "wf-001"
        assert "issues" in data
        assert "insights" in data
        assert "confidence" in data
=======
        body = response.json()
        assert body["success"] is True
        # P1-6 契约: 字段在 data 下
        data = body["data"]
        assert data["workflow_id"] == "wf-001", (
            f"workflow_id 必须回显请求值, 实际: {data.get('workflow_id')!r}"
        )
        assert isinstance(data["issues"], list)
        assert data["issues"] == [], "无 code/test_results 时 issues 应为空列表"
        assert isinstance(data["insights"], list)
        # confidence 硬编码 0.85 (api.py:1723)
        assert data["confidence"] == 0.85, (
            f"confidence 应为 0.85 (api.py:1723), 实际: {data['confidence']}"
        )
>>>>>>> Stashed changes
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

    def test_diagnose_workflow_with_test_results(self, client, auth_headers):
        """正向: 1 个测试失败 → 1 个 issue + 完整字段结构。"""
        test_results = {
            "failures": [
                {
                    "test_name": "登录测试失败",
                    "error_message": "AssertionError: 预期状态码200，实际401",
                    "location": "/auth/login",
                }
            ]
        }
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "test_results": test_results},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["workflow_id"] == "wf-001"
        # [真实业务] 提交1个failure → issues必须有1个发现 (defect_analyzer.analyze_test_results)
        # 旧版 assert len >= 0 是 tautology (恒真), 掩盖分析逻辑失效
        assert isinstance(data["issues"], list)
        assert len(data["issues"]) == 1, (
            f"提交1个测试失败应产生1个issue, 实际 {len(data['issues'])} — "
            "若为0说明 defect_analyzer.analyze_test_results 未正确分析"
        )
        issue = data["issues"][0]
        # issue 字段结构必须完整 (源码 api.py:1684-1691)
        required_fields = {"severity", "message", "code_location",
                           "suggestion", "confidence", "description"}
        missing = required_fields - set(issue.keys())
        assert not missing, f"issue 缺字段: {missing}"
        # message 必须含提交的 test_name
        assert "登录测试失败" in issue["message"], (
            f"issue.message 应含 test_name '登录测试失败', 实际: '{issue['message']}'"
        )
        # description 必须含提交的 error_message
        assert "401" in issue["description"], (
            f"issue.description 应含 error_message 中的 '401', 实际: '{issue['description']}'"
        )
        # severity 必须是有效值
        valid_severities = {"critical", "high", "medium", "low", "info"}
        assert issue["severity"].lower() in valid_severities, (
            f"severity 必须是有效值 {valid_severities}, 实际: '{issue['severity']}'"
        )
        # confidence ∈ [0, 1]
        assert 0.0 <= issue["confidence"] <= 1.0, (
            f"confidence 越界: {issue['confidence']}"
        )

    def test_diagnose_workflow_with_code(self, client, auth_headers):
        """正向: 提交代码 → issues 为 list, 每项结构完整 (若非空)。"""
        code = """
def login(username, password):
    if username == "admin" and password == "password":
        return True
    return False
"""
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "code": code},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["workflow_id"] == "wf-001"
        assert isinstance(data["issues"], list)
        # 代码分析可能产出 findings; 若有, 校验结构
        required_fields = {"severity", "message", "code_location",
                           "suggestion", "confidence", "description"}
        for issue in data["issues"]:
            missing = required_fields - set(issue.keys())
            assert not missing, f"issue 缺字段: {missing}"

    def test_diagnose_workflow_with_code_and_results(self, client, auth_headers):
        """正向: code + test_results → issues 来自两个分析源, 类型为 list。"""
        code = """
def process_data(data):
    return data["value"]
"""
        test_results = {
            "failures": [
                {"test_name": "空数据测试", "error_message": "KeyError: 'value'", "location": "process_data"}
            ]
        }
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001", "code": code, "test_results": test_results},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
=======
        data = response.json()["data"]
>>>>>>> Stashed changes
        assert data["workflow_id"] == "wf-001"
        assert isinstance(data["issues"], list)
        # 至少有 test_results 贡献的 1 个 issue (defect_analyzer.analyze_test_results)
        assert len(data["issues"]) >= 1, (
            f"提交 1 个 failure 应至少产生 1 个 issue, 实际: {len(data['issues'])}"
        )
        # 至少 1 个 issue 提到 KeyError/空数据测试
        messages = " ".join(i["message"] for i in data["issues"])
        assert "空数据测试" in messages, (
            f"issues 应含 test_name '空数据测试', 实际 messages: {messages}"
        )

    def test_diagnose_workflow_unauthorized(self, client):
        """负向: 无认证 → 401。"""
        response = client.post("/diagnose/workflow", json={"workflow_id": "wf-001"})
        assert response.status_code == 401

    def test_diagnose_workflow_insights_structure(self, client, auth_headers):
        """边界: insights 必须是 list, 每项结构完整 (非空时校验, 空时也断言类型)。

        旧版 for 循环在 insights 为空时不执行 → tautology (恒真)。
        修复: 显式断言 isinstance(list); 非空时校验字段。
        """
        response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
<<<<<<< Updated upstream
        resp = response.json()
        data = resp.get("data", resp)
        for insight in data.get("insights", []):
            assert "title" in insight
            assert "description" in insight
            assert "severity" in insight
            assert "recommendation" in insight
            assert "confidence" in insight
=======
        data = response.json()["data"]
        # 显式类型断言 (非 tautology: 若 insights 为 None/缺失则失败)
        assert isinstance(data["insights"], list), (
            f"insights 必须是 list, 实际: {type(data.get('insights'))}"
        )
        required = {"title", "description", "severity", "recommendation", "confidence"}
        for insight in data["insights"]:
            missing = required - set(insight.keys())
            assert not missing, f"insight 缺字段: {missing}"
            assert 0.0 <= insight["confidence"] <= 1.0
>>>>>>> Stashed changes


class TestTestEngineEndToEnd:
    """测试引擎完整端到端测试"""

    def test_full_test_diagnose_flow(self, client, auth_headers):
        """全流程: /test/execute → 构建 failures → /diagnose/workflow。

        /health (200, passed=True) + /users (401 无 auth, passed=False)。
        旧版仅断言 workflow_id, 不校验 execute 一致性与 diagnose 联动。
        """
        execute_response = client.post(
            "/test/execute",
            json={
                "test_cases": [
                    {"name": "健康检查", "protocol": "http", "method": "GET", "url": "/health"},
                    {"name": "用户列表", "protocol": "http", "method": "GET", "url": "/users"},
                ]
            },
            headers=auth_headers,
        )
        assert execute_response.status_code == 200
<<<<<<< Updated upstream
        execute_resp = execute_response.json()
        execute_data = execute_resp.get("data", execute_resp)
=======
        execute_data = execute_response.json()["data"]
>>>>>>> Stashed changes

        # ---- 一致性校验 ----
        assert execute_data["total_tests"] == 2
        assert execute_data["passed_tests"] + execute_data["failed_tests"] == 2
        assert len(execute_data["results"]) == 2
        # /health 应通过, /users (用例无 auth header) 应失败
        results_by_name = {r["test_case_name"]: r for r in execute_data["results"]}
        assert results_by_name["健康检查"]["passed"] is True, (
            "/health 应通过 (server live)"
        )
        assert results_by_name["用户列表"]["passed"] is False, (
            f"/users 用例无 auth header 应 401 失败, 实际 passed="
            f"{results_by_name['用户列表']['passed']}"
        )

        # ---- 构建 failures 并联动 diagnose ----
        test_results = {
            "failures": [
                {
                    "test_name": tc["test_case_name"],
                    "error_message": "测试未通过" if not tc["passed"] else "",
                    "location": "test",
                }
                for tc in execute_data["results"]
                if not tc["passed"]
            ]
        }
        # 至少有 1 个失败 (用户列表) → diagnose 应产出 issue
        assert len(test_results["failures"]) >= 1

        diagnose_response = client.post(
            "/diagnose/workflow",
            json={"workflow_id": "wf-e2e-test", "test_results": test_results},
            headers=auth_headers,
        )
        assert diagnose_response.status_code == 200
<<<<<<< Updated upstream
        diagnose_resp = diagnose_response.json()
        diagnose_data = diagnose_resp.get("data", diagnose_resp)
=======
        diagnose_data = diagnose_response.json()["data"]
>>>>>>> Stashed changes
        assert diagnose_data["workflow_id"] == "wf-e2e-test"
        assert isinstance(diagnose_data["issues"], list)
        assert len(diagnose_data["issues"]) >= 1, (
            f"提交 {len(test_results['failures'])} 个 failure 应产出 issue, "
            f"实际: {len(diagnose_data['issues'])}"
        )

    def test_generate_and_execute_flow(self, client, auth_headers):
        """全流程: /test/generate → /test/execute。

        旧版仅断言 status==200, 不校验 generate 契约与 execute 联动。
        """
        spec = {
            "name": "监控API测试",
            "description": "监控相关接口",
            "endpoints": [
                {"method": "GET", "path": "/monitoring/metrics", "description": "获取监控指标"}
            ],
        }
        generate_response = client.post("/test/generate", json=spec, headers=auth_headers)
        assert generate_response.status_code == 200
<<<<<<< Updated upstream
        generate_resp = generate_response.json()
        generate_data = generate_resp.get("data", generate_resp)
=======
        gen_body = generate_response.json()
        gen_data = gen_body["data"]
        # ---- generate 契约 + 一致性 ----
        assert gen_data["total_generated"] == len(gen_data["test_cases"]), (
            f"total_generated({gen_data['total_generated']}) != "
            f"len(test_cases)({len(gen_data['test_cases'])})"
        )
>>>>>>> Stashed changes

        if gen_data["total_generated"] > 0:
            test_cases = [
                {
                    "name": tc["name"],
                    "protocol": "http",
                    "method": "GET",
                    "url": "/monitoring/metrics",
                }
                for tc in gen_data["test_cases"]
            ]
            execute_response = client.post(
                "/test/execute",
                json={"test_cases": test_cases},
                headers=auth_headers,
            )
            assert execute_response.status_code == 200
            exec_data = execute_response.json()["data"]
            # ---- execute 一致性 ----
            assert exec_data["total_tests"] == len(test_cases)
            assert exec_data["passed_tests"] + exec_data["failed_tests"] == exec_data["total_tests"]
            assert len(exec_data["results"]) == len(test_cases)
