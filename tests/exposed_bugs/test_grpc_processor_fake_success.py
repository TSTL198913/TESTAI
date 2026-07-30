"""
P0-5 GrpcProcessor 假成功验证测试

验证 GrpcProcessor.process() 方法是否正确实现。
当前实现返回硬编码 {"message": "Success"} 而不执行真实 gRPC 调用，
导致 gRPC 步骤永远"成功"但实际未执行任何操作。

关联缺陷: TECH_DEBT_P0_5
"""
import pytest
from pathlib import Path


class TestGrpcProcessorFakeSuccess:
    """验证 GrpcProcessor 不应假成功"""

    @pytest.fixture
    def processor_file(self) -> Path:
        return Path(__file__).parent.parent.parent / "src" / "engine" / "processor" / "grpc.py"

    def test_processor_file_exists(self, processor_file: Path):
        """验证 GrpcProcessor 文件存在"""
        assert processor_file.exists(), "src/engine/processor/grpc_processor.py 不存在"

    def test_no_hardcoded_success_message(self, processor_file: Path):
        """
        验证 GrpcProcessor 不返回硬编码成功消息。
        
        业务规则:
        - GrpcProcessor.process() 不应返回 {"message": "Success"} 硬编码
        - 真实 gRPC 调用应有错误处理，失败时抛出异常
        - 未实现功能应抛出 NotImplementedError
        """
        if not processor_file.exists():
            pytest.skip("grpc_processor.py 不存在")

        content = processor_file.read_text(encoding="utf-8")

        # 检查是否有硬编码成功消息
        fake_success_patterns = [
            '"message": "Success"',
            "'message': 'Success'",
            '"message": "success"',
            "'message': 'success'",
            "message.*Success",
        ]

        has_fake_success = False
        for pattern in fake_success_patterns:
            import re
            if re.search(pattern, content, re.IGNORECASE):
                has_fake_success = True
                print(f"⚠️  发现假成功模式: {pattern}")
                break

        # 检查是否有 NotImplementedError 或真实 gRPC 调用
        has_not_implemented = "NotImplementedError" in content
        has_grpc_call = any([
            "grpc." in content,
            "insecure_channel" in content,
            "secure_channel" in content,
            "_channel" in content,
        ])

        print(f"\n🔍 GrpcProcessor 检查结果:")
        print(f"   假成功模式: {'❌ 存在' if has_fake_success else '✅ 不存在'}")
        print(f"   NotImplementedError: {'✅ 存在' if has_not_implemented else '❌ 不存在'}")
        print(f"   gRPC 调用: {'✅ 存在' if has_grpc_call else '❌ 不存在'}")

        # 断言: 不应有硬编码成功消息
        assert not has_fake_success, (
            "❌ P0-5 缺陷: GrpcProcessor 返回硬编码成功消息\n"
            "当前实现: {'message': 'Success'} (假成功)\n"
            "修复方案 A: 实现真实 gRPC 调用\n"
            "修复方案 B (推荐): 抛出 NotImplementedError\n"
            "真实 gRPC 不可用时，应报错而非假成功"
        )

    def test_get_channel_not_empty(self, processor_file: Path):
        """
        验证 _get_channel 方法不是空实现。
        
        业务规则:
        - _get_channel() 不应仅有 pass
        - 应有真实的 channel 创建逻辑
        """
        if not processor_file.exists():
            pytest.skip("grpc_processor.py 不存在")

        content = processor_file.read_text(encoding="utf-8")

        # 检查是否有 def _get_channel 方法
        has_get_channel = "def _get_channel" in content
        
        if not has_get_channel:
            print("⚠️  未找到 _get_channel 方法")
            return

        # 检查方法体是否为空
        import re
        # 查找 _get_channel 方法定义
        match = re.search(
            r'def _get_channel.*?def |def _get_channel.*?\Z',
            content,
            re.DOTALL
        )
        
        if match:
            method_body = match.group(0)
            # 检查是否只有 pass
            if method_body.strip().endswith("pass") or method_body.count('\n') <= 2:
                pytest.fail(
                    "❌ P0-5 缺陷: _get_channel 方法是空实现\n"
                    "应实现真实 gRPC channel 创建逻辑\n"
                    "或抛出 NotImplementedError"
                )

    def test_process_raises_not_implemented_for_unavailable_grpc(self, processor_file: Path):
        """
        验证 process 方法在 gRPC 不可用时抛出异常。
        
        业务规则:
        - 当 gRPC 服务不可用时，应抛出异常
        - 不应返回假成功
        """
        if not processor_file.exists():
            pytest.skip("grpc_processor.py 不存在")

        content = processor_file.read_text(encoding="utf-8")

        # 检查是否有异常抛出
        has_raise = "raise " in content
        has_not_implemented = "NotImplementedError" in content

        assert has_raise or has_not_implemented, (
            "❌ P0-5 缺陷: GrpcProcessor.process() 不抛出异常\n"
            "当 gRPC 不可用时，应 raise NotImplementedError 或其他异常\n"
            "当前假成功实现会导致流程静默通过，掩盖真实错误"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])