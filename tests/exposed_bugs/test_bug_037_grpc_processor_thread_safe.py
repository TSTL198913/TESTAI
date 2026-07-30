import pytest
import threading
from src.engine.processor.grpc import GrpcProcessor


class TestGrpcProcessorThreadSafe:
    def test_channels_dict_is_thread_safe(self):
        processor = GrpcProcessor()
        results = []

        def get_channel_thread():
            try:
                channel = processor._get_channel("localhost", 50051)
                results.append((threading.current_thread().name, channel))
            except Exception:
                pass

        threads = [threading.Thread(target=get_channel_thread, name=f"Thread-{i}") for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10, "All threads should complete without errors"