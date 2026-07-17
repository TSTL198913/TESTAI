# trigger_test.py
from src.worker.tasks import verify_connection

print("正在发送任务到 Redis...")
task = verify_connection.delay("Hello Distributed World!")

print(f"任务已入队！Task ID: {task.id}")
print("请观察 Worker 终端的输出...")