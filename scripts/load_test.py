# load_test.py
import time
from src.worker.tasks import run_test_pipeline


def run_stress_test(num_tasks=100):
    print(f"🚀 开始压力测试：并发投递 {num_tasks} 个任务...")
    start_time = time.time()

    for i in range(num_tasks):
        # 直接调用 delay，模拟高并发入队
        run_test_pipeline.delay({
            "step_id": f"stress_test_{i}",
            "description": f"测试场景: 接口稳定性。",
            "method": "GET",
            "url": "https://httpbin.org/status/200",
            "assertions": [{"check": "status_code", "expected": 200}]
        }, trace_id=f"stress_{i}")

    end_time = time.time()
    print(f"✅ 任务投递完成，耗时: {end_time - start_time:.2f}s")


if __name__ == "__main__":
    run_stress_test(50)  # 先从 50 个任务开始