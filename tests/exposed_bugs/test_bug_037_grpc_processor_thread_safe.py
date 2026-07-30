import pytest
import threading
from src.engine.processor.grpc import GrpcProcessor


class TestGrpcProcessorThreadSafe:
    def test_channels_dict_is_thread_safe(self):
        """验证并发访问 _get_channel 时，所有线程都正确抛出 NotImplementedError"""
        processor = GrpcProcessor()
        results = []
        errors = []

        def get_channel_thread():
            try:
                channel = processor._get_channel("localhost", 50051)
                results.append((threading.current_thread().name, channel))
            except NotImplementedError as e:
                errors.append((threading.current_thread().name, str(e)))

        threads = [threading.Thread(target=get_channel_thread, name=f"Thread-{i}") for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 修复后：所有线程都应该抛出 NotImplementedError（因为 gRPC 未实现）
        assert len(results) == 0, "No threads should succeed when gRPC is not implemented"
        assert len(errors) == 10, f"All 10 threads should raise NotImplementedError, got {len(errors)} errors"
        
        # 验证错误消息
        for thread_name, error_msg in errors:
            assert "gRPC channel not implemented" in error_msg, f"Thread {thread_name}: unexpected error message"