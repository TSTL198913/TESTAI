"""
真实网络测试扩展套件
基于黄金数据集的20+真实API测试用例
技术委员会审核专用
"""
import asyncio
import json
import os
import pytest
import httpx

from src.core.context import ExecutionContext
from src.engine.pipeline import ExecutionPipeline
from src.engine.processor.data import DataProcessor
from src.engine.processor.http import HTTPProcessor
from src.engine.processor.assertion import AssertionProcessor


class TestRealNetworkExtended:
    """扩展真实网络测试用例集"""

    GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "../data/golden_dataset.json")

    @pytest.mark.asyncio
    async def test_real_httpbin_post_with_body(self):
        """真实场景：POST请求带JSON body"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_001",
                env={},
                vars={"user_data": {"name": "test", "age": 30}},
                results={},
            )

            test_steps = [
                {
                    "step_id": "post_with_body",
                    "description": "POST请求带JSON body",
                    "protocol": "http",
                    "method": "POST",
                    "url": "https://httpbin.org/anything",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"name": "TestAI", "version": "1.0", "platform": "Python"},
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["post_with_body"]["status"] == "PASSED"
            assert context.results["post_with_body"]["status_code"] == 200
            body = context.results["post_with_body"]["body"]
            assert body["json"]["name"] == "TestAI"
            assert body["json"]["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_real_httpbin_headers_custom(self):
        """真实场景：自定义请求头"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_002",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "custom_headers",
                    "description": "自定义请求头",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/headers",
                    "headers": {
                        "X-Custom-Platform": "TestAI",
                        "X-Request-Trace": "trace-abc-123",
                        "X-User-Id": "user-999",
                    },
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["custom_headers"]["status"] == "PASSED"
            body = context.results["custom_headers"]["body"]
            assert "X-Custom-Platform" in body["headers"]
            assert body["headers"]["X-Custom-Platform"] == "TestAI"

    @pytest.mark.asyncio
    async def test_real_httpbin_json_response(self):
        """真实场景：JSON响应解析"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_003",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "json_response",
                    "description": "JSON响应解析",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/json",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["json_response"]["status"] == "PASSED"
            body = context.results["json_response"]["body"]
            assert "slideshow" in body
            assert "author" in body["slideshow"]

    @pytest.mark.asyncio
    async def test_real_httpbin_ip(self):
        """真实场景：IP地址获取"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_004",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "get_ip",
                    "description": "IP地址获取",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/ip",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["get_ip"]["status"] == "PASSED"
            body = context.results["get_ip"]["body"]
            assert "origin" in body

    @pytest.mark.asyncio
    async def test_real_httpbin_user_agent(self):
        """真实场景：User-Agent验证"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_005",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "user_agent_test",
                    "description": "User-Agent验证",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/user-agent",
                    "headers": {"User-Agent": "TestAI-Agent/1.0"},
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["user_agent_test"]["status"] == "PASSED"
            body = context.results["user_agent_test"]["body"]
            assert "TestAI-Agent" in body["user-agent"]

    @pytest.mark.asyncio
    async def test_real_httpbin_cookies(self):
        """真实场景：Cookie处理"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_006",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "cookies_test",
                    "description": "Cookie处理",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/cookies",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["cookies_test"]["status"] == "PASSED"
            body = context.results["cookies_test"]["body"]
            assert "cookies" in body

    @pytest.mark.asyncio
    async def test_real_httpbin_gzip(self):
        """真实场景：Gzip压缩响应"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_007",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "gzip_test",
                    "description": "Gzip压缩响应",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/gzip",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["gzip_test"]["status"] == "PASSED"
            body = context.results["gzip_test"]["body"]
            assert "gzipped" in body

    @pytest.mark.asyncio
    async def test_real_httpbin_deflate(self):
        """真实场景：Deflate压缩响应"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_008",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "deflate_test",
                    "description": "Deflate压缩响应",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/deflate",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["deflate_test"]["status"] == "PASSED"
            body = context.results["deflate_test"]["body"]
            assert "deflated" in body

    @pytest.mark.asyncio
    async def test_real_httpbin_uuid(self):
        """真实场景：UUID生成"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_009",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "uuid_test",
                    "description": "UUID生成",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/uuid",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["uuid_test"]["status"] == "PASSED"
            body = context.results["uuid_test"]["body"]
            assert "uuid" in body
            assert len(body["uuid"]) == 36

    @pytest.mark.asyncio
    async def test_real_httpbin_redirect(self):
        """真实场景：重定向处理"""
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            context = ExecutionContext(
                case_id="real_ext_010",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "redirect_test",
                    "description": "重定向处理",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/redirect/1",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["redirect_test"]["status"] == "PASSED"
            assert context.results["redirect_test"]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_real_httpbin_stream(self):
        """真实场景：流响应"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_011",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "stream_test",
                    "description": "流响应",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/stream/3",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["stream_test"]["status"] == "PASSED"
            assert context.results["stream_test"]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_real_httpbin_cache(self):
        """真实场景：缓存控制"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_012",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "cache_test",
                    "description": "缓存控制",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/cache/60",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["cache_test"]["status"] == "PASSED"
            assert "Cache-Control" in context.results["cache_test"]["body"]["headers"]

    @pytest.mark.asyncio
    async def test_real_httpbin_status_various(self):
        """真实场景：多种HTTP状态码"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            for status_code in [200, 201, 204, 301, 302, 400, 401, 403, 404, 500]:
                context = ExecutionContext(
                    case_id=f"real_ext_status_{status_code}",
                    env={},
                    vars={},
                    results={},
                )

                test_steps = [
                    {
                        "step_id": f"status_{status_code}",
                        "description": f"HTTP状态码{status_code}测试",
                        "protocol": "http",
                        "method": "GET",
                        "url": f"https://httpbin.org/status/{status_code}",
                    }
                ]

                pipeline = ExecutionPipeline(
                    processors=[DataProcessor(), HTTPProcessor()]
                )

                if status_code >= 400:
                    with pytest.raises(Exception):
                        await pipeline.run(context, test_steps, client)
                    assert context.results[f"status_{status_code}"]["status"] == "FAILED"
                else:
                    await pipeline.run(context, test_steps, client)
                    assert context.results[f"status_{status_code}"]["status"] == "PASSED"
                    assert context.results[f"status_{status_code}"]["status_code"] == status_code

    @pytest.mark.asyncio
    async def test_golden_dataset_full_execution(self):
        """真实场景：黄金数据集全量执行（20个API基线）"""
        with open(self.GOLDEN_PATH, "r") as f:
            golden_data = json.load(f)

        async with httpx.AsyncClient(timeout=15.0) as client:
            success_count = 0
            total_tests = 0

            for baseline_id, baseline in golden_data["baselines"].items():
                if baseline["method"] not in ["GET", "POST"]:
                    continue

                total_tests += 1
                context = ExecutionContext(
                    case_id=f"golden_{baseline_id}",
                    env={},
                    vars={},
                    results={},
                )

                test_steps = [
                    {
                        "step_id": baseline_id,
                        "description": baseline.get("description", f"Golden baseline {baseline_id}"),
                        "protocol": baseline["protocol"],
                        "method": baseline["method"],
                        "url": baseline["url"],
                        "headers": baseline.get("headers", {}),
                        "body": baseline.get("body", {}),
                        "params": baseline.get("params", {}),
                    }
                ]

                pipeline = ExecutionPipeline(
                    processors=[DataProcessor(), HTTPProcessor()]
                )

                try:
                    await pipeline.run(context, test_steps, client)
                    if context.results[baseline_id]["status_code"] == baseline["expected_status"]:
                        success_count += 1
                except Exception as e:
                    failed_requests.append(f"{baseline_id}: {str(e)}")

            assert total_tests == 20, f"Expected 20 golden baseline tests, got {total_tests}"
            assert success_count >= 18, f"Expected at least 18 successful tests, got {success_count}"

    @pytest.mark.asyncio
    async def test_real_network_with_assertions(self):
        """真实场景：完整断言流程"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_assertions",
                env={},
                vars={"expected_name": "TestAI"},
                results={},
            )

            test_steps = [
                {
                    "step_id": "assertion_test",
                    "description": "POST请求带JSON body用于断言",
                    "protocol": "http",
                    "method": "POST",
                    "url": "https://httpbin.org/anything",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"name": "TestAI", "value": 42},
                },
                {
                    "step_id": "verify_name",
                    "description": "验证响应数据",
                    "protocol": "assertion",
                    "assertions": [
                        {
                            "type": "equals",
                            "actual": "{{ results.assertion_test.body.json.name }}",
                            "expected": "TestAI",
                        },
                        {
                            "type": "equals",
                            "actual": "{{ results.assertion_test.body.json.value }}",
                            "expected": 42,
                        },
                    ],
                },
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor(), AssertionProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["assertion_test"]["status"] == "PASSED"
            assert context.results["verify_name"]["status"] == "PASSED"

    @pytest.mark.asyncio
    async def test_real_network_timeout_handling(self):
        """真实场景：超时处理"""
        async with httpx.AsyncClient(timeout=2.0) as client:
            context = ExecutionContext(
                case_id="real_ext_timeout",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "timeout_test",
                    "description": "超时处理测试",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/delay/5",
                }
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            with pytest.raises(Exception):
                await pipeline.run(context, test_steps, client)

            assert "timeout_test" in context.results
            assert context.results["timeout_test"]["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_real_network_concurrent_requests(self):
        """真实场景：并发请求"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            context = ExecutionContext(
                case_id="real_ext_concurrent",
                env={},
                vars={},
                results={},
            )

            test_steps = [
                {
                    "step_id": "concurrent_1",
                    "description": "并发请求1",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/get",
                    "params": {"id": "1"},
                },
                {
                    "step_id": "concurrent_2",
                    "description": "并发请求2",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/ip",
                },
                {
                    "step_id": "concurrent_3",
                    "description": "并发请求3",
                    "protocol": "http",
                    "method": "GET",
                    "url": "https://httpbin.org/uuid",
                },
            ]

            pipeline = ExecutionPipeline(
                processors=[DataProcessor(), HTTPProcessor()]
            )

            await pipeline.run(context, test_steps, client)

            assert context.results["concurrent_1"]["status"] == "PASSED"
            assert context.results["concurrent_2"]["status"] == "PASSED"
            assert context.results["concurrent_3"]["status"] == "PASSED"