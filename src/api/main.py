"""
[已废弃] 测试+AI平台入口 — 请勿用于新部署。

此模块是旧的 API 入口 (src.api.main:app), 仅注册 6 条基础路由,
不包含治理端点 (/governance/*)。当前治理平台入口为 src.platform.api:app
(60 条路由, 含治理闭环/审批/监控/基线等)。

隔离策略 (隔离不删):
  - 此文件保留但不再作为启动入口 (start.sh / Dockerfile / README 均已改用 src.platform.api:app)
  - 硬依赖 src.engine.pipeline / src.storage.repository 属"其他方向"模块, 不做隔离
    (若这些模块被移除, 此文件自然不可加载, 但不影响治理平台入口 src.platform.api:app)
  - 由 test_entry_point_consistency.py 守卫, 防止误改回旧入口

如需迁移此文件中的独有功能到 src.platform.api, 请先确认 api.py 中已有等价端点。
"""
import time
import uuid
import logging
import warnings
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.api.dependencies import get_current_user, require_admin, require_tester
from src.engine.pipeline import ExecutionPipeline
from src.models.contract import HttpRequest
from src.platform.metrics import APIMetrics
from src.security.auth import User
from src.storage.repository import ResultRepository
from src.worker.tasks import run_test_pipeline

# P2-6 废弃入口: 运行时 DeprecationWarning, 使任何误用旧入口 (src.api.main:app)
# 的部署/脚本在导入时即被显式告警, 而非仅在文档中标注。当前平台启动入口为
# src.platform.api:app (apps/server/pyproject.toml 的 testai-server 脚本)。
warnings.warn(
    "src.api.main is the DEPRECATED legacy API entry point (6 routes, no "
    "/governance/* endpoints). The active platform entry is src.platform.api:app "
    "(60 routes, full governance loop). Do not wire start.sh/Dockerfile/README to "
    "src.api.main; this module will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

metrics = APIMetrics()
repo = ResultRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        metrics.set_system_health("api", True)
        metrics.set_system_health("worker", True)
        metrics.set_system_health("governance", True)
        logger.info("TestAI Engine Service started successfully")
    except Exception as e:
        logger.error(f"Service startup failed: {e}")
        metrics.set_system_health("api", False)
        raise
    yield
    metrics.set_system_health("api", False)
    logger.info("TestAI Engine Service shutting down")


app = FastAPI(title="TestAI Engine Service", lifespan=lifespan)


def get_pipeline():
    return ExecutionPipeline(processors=[], repository=repo)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    endpoint = request.url.path
    method = request.method
    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        metrics.record_request(endpoint, method, response.status_code, duration)
        return response
    except Exception as e:
        duration = time.time() - start_time
        metrics.record_request(endpoint, method, 500, duration)
        logger.error(f"Request failed: {e}")
        raise


@app.get("/health")
async def health_check():
    components = {
        "api": True,
        "worker": True,
        "governance": True,
        "repository": True,
    }
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": components,
    }


@app.get("/metrics")
async def prometheus_metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/execute")
async def execute_test(
    request: HttpRequest,
    current_user: User = Depends(require_tester),
):
    trace_id = str(uuid.uuid4())[:8]
    try:
        request_dict = request.model_dump(mode="json")
        request_dict["_trace_id"] = trace_id
        request_dict["_requester"] = current_user.username
        task = run_test_pipeline.delay(request_dict)
        return {
            "status": "queued",
            "task_id": task.id,
            "trace_id": trace_id,
            "message": "流水线已入队，请关注 MongoDB 数据更新",
        }
    except Exception as e:
        logger.error(f"Task submission failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "trace_id": trace_id,
            "message": f"任务投递失败: {str(e)}",
        }, 500


@app.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    metrics.record_task_status_check()
    try:
        result = run_test_pipeline.AsyncResult(task_id)
        if result.ready():
            if result.successful():
                return {"task_id": task_id, "status": "completed", "result": str(result.result)}
            else:
                return {"task_id": task_id, "status": "failed", "error": str(result.result)}, 500
        return {"task_id": task_id, "status": "pending"}
    except Exception as e:
        logger.error(f"Task status check failed: {e}", exc_info=True)
        return {"task_id": task_id, "status": "unknown", "error": str(e)}, 404


@app.get("/baselines")
async def list_baselines(
    current_user: User = Depends(get_current_user),
):
    try:
        baselines = await repo.list_baselines() if hasattr(repo, 'list_baselines') else []
        return {"baselines": baselines, "count": len(baselines)}
    except Exception as e:
        logger.error(f"Baseline list failed: {e}")
        return {"baselines": [], "count": 0, "error": str(e)}, 500


@app.post("/evaluate")
async def evaluate_results(
    request: HttpRequest,
    current_user: User = Depends(require_admin),
):
    trace_id = str(uuid.uuid4())[:8]
    try:
        from src.ai.evaluator import AIEvaluator
        evaluator = AIEvaluator()
        request_data = request.model_dump(mode="json", exclude={"steps"})
        output_text = request_data.get("actual_output") or str(request_data)
        expected_text = request_data.get("expected_baseline", "")
        result = evaluator.evaluate(str(output_text), str(expected_text))
        metrics.record_evaluate("auto", 0.0)
        return {
            "trace_id": trace_id,
            "evaluation": result.to_dict(),
        }
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        metrics.record_evaluate_error("auto")
        return {"trace_id": trace_id, "error": str(e)}, 500