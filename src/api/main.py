import uuid

from fastapi import FastAPI

from src.engine.pipeline import ExecutionPipeline
from src.storage.repository import ResultRepository
from src.models.contract import HttpRequest  # 假设这是你的请求模型
from src.worker.tasks import run_test_pipeline

app = FastAPI(title="TestAI Engine Service")

# 实例化 Repository (在实际生产中，建议放入 lifespan 中进行生命周期管理)
repo = ResultRepository()


def get_pipeline():
    # 注入 repository 到 pipeline
    return ExecutionPipeline(
        processors=[],  # 这里按需添加你的 Processor
        repository=repo
    )


@app.post("/execute")
async def execute_test(request: HttpRequest):
    trace_id = str(uuid.uuid4())[:8]
    try:
        task = run_test_pipeline.delay(request.model_dump(mode='json'), trace_id)
        return {
            "status": "queued",
            "task_id": task.id,
            "trace_id": trace_id,
            "message": "流水线已入队，请关注 MongoDB 数据更新"
        }
    except Exception as e:
        return {
            "status": "failed",
            "trace_id": trace_id,
            "message": f"任务投递失败: {str(e)}"
        }, 500