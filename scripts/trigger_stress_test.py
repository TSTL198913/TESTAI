import asyncio
import uuid
from src.worker.tasks import run_test_pipeline


async def fire_tasks(count: int):
    # 模拟构建 50 个符合 schema 的请求
    tasks = []
    for i in range(count):
        request_data = {
            # 【关键修改】：显式添加 pipeline 定义
            "pipeline": ["data", "request", "assertion"],
            "steps": [
                {"step_id": f"stress_test_{i}", "description": "Concurrency Test",
                 "params": {"url": f"https://httpbin.org/status/{i*100}"}}
            ]
        }
        # 直接调用 task.delay 或者在此处模拟
        # 这里为了测试异步上下文，我们手动触发
        tasks.append(asyncio.to_thread(run_test_pipeline.delay, request_data))

    print(f"🚀 瞬间并发触发: {count} 个任务")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(fire_tasks(5))