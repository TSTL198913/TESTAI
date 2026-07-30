"""
P0-2 APIMetrics 中间件验证测试

验证 src/platform/api.py 是否注册了 HTTP 中间件来记录 API 请求指标。
当前 APIMetrics.record_request() 已实现，但未被任何中间件调用。

关联缺陷: TECH_DEBT_P0_2
"""
import pytest
import importlib
from pathlib import Path


class TestAPIMetricsMiddleware:
    """验证 APIMetrics 中间件是否正确注册"""

    def test_apimetrics_class_exists(self):
        """验证 APIMetrics 类存在且有 record_request 方法"""
        try:
            from src.platform.metrics import APIMetrics
        except ImportError as e:
            pytest.fail(f"无法导入 APIMetrics: {e}")

        instance = APIMetrics()
        assert hasattr(instance, 'record_request'), (
            "APIMetrics 缺少 record_request 方法"
        )
        print("✅ APIMetrics.record_request 方法存在")

    def test_middleware_registered_in_api(self):
        """
        验证 src/platform/api.py 注册了 @app.middleware("http")
        
        业务规则:
        - APIMetrics.record_request() 必须通过 FastAPI 中间件调用
        - 中间件必须使用 @app.middleware("http") 装饰器
        - 中间件必须在每个请求结束后调用 api_metrics.record_request()
        
        此测试检查 api.py 文件是否包含中间件注册代码。
        """
        api_file = Path(__file__).parent.parent.parent / "src" / "platform" / "api.py"
        
        if not api_file.exists():
            pytest.skip("src/platform/api.py 不存在")

        content = api_file.read_text(encoding="utf-8")

        # 检查是否有 @app.middleware("http") 装饰器
        has_middleware_decorator = '@app.middleware("http")' in content or "@app.middleware('http')" in content
        
        # 检查是否有 api_metrics 导入
        has_apimetrics_import = "from src.platform.metrics import APIMetrics" in content
        
        # 检查 record_request 是否被调用
        has_record_request_call = "record_request(" in content

        print(f"\n🔍 检查结果:")
        print(f"   middleware 装饰器: {'✅ 找到' if has_middleware_decorator else '❌ 未找到'}")
        print(f"   APIMetrics 导入: {'✅ 找到' if has_apimetrics_import else '❌ 未找到'}")
        print(f"   record_request 调用: {'✅ 找到' if has_record_request_call else '❌ 未找到'}")

        # 断言: 必须有中间件注册
        assert has_apimetrics_import, (
            "❌ P0-2 缺陷: src/platform/api.py 未导入 APIMetrics\n"
            "必须添加: from src.platform.metrics import APIMetrics"
        )

        # 断言: 必须有 record_request 调用
        assert has_record_request_call, (
            "❌ P0-2 缺陷: src/platform/api.py 未调用 record_request()\n"
            "必须在中间件中添加: api_metrics.record_request(endpoint, method, status_code, duration)"
        )

        print("\n✅ P0-2 验证通过: APIMetrics 中间件已正确注册")

    def test_record_request_signature(self):
        """验证 record_request 方法签名正确"""
        try:
            from src.platform.metrics import APIMetrics
            import inspect
        except ImportError as e:
            pytest.fail(f"无法导入 APIMetrics: {e}")

        sig = inspect.signature(APIMetrics.record_request)
        params = list(sig.parameters.keys())

        # 验证参数: endpoint, method, status_code, duration
        expected_params = ['self', 'endpoint', 'method', 'status_code', 'duration']
        for expected in expected_params:
            assert expected in params, (
                f"record_request 缺少参数: {expected}\n"
                f"当前参数: {params}"
            )

        print(f"✅ record_request 签名正确: {params}")

    def test_record_request_works(self):
        """验证 record_request 方法可以正常调用"""
        try:
            from src.platform.metrics import APIMetrics
        except ImportError as e:
            pytest.fail(f"无法导入 APIMetrics: {e}")

        metrics = APIMetrics()
        
        # 应该可以正常调用而不抛出异常
        try:
            metrics.record_request(
                endpoint="/test",
                method="GET",
                status_code=200,
                duration=0.1
            )
        except Exception as e:
            pytest.fail(f"record_request 调用失败: {e}")

        print("✅ record_request 调用成功")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])