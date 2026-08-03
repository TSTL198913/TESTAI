# /execute 主路径同步治理回退（Gap 1 收敛）

## Context（为什么做这个）

AI 治理平台的根因缺陷："平台叫治理但日常不治理"。`/execute` 主路径（`src/platform/api.py:1715-1743`）只调 `run_test_pipeline.delay()` 把任务丢给 Celery，自身不触发治理。治理闭环（`GovernanceOrchestrator.execute_governance_flow` 六步）只在 Celery worker 异步任务体（`src/worker/tasks.py:44-68`）失败时才触发。

后果：**dev/无 Redis 环境下 `/execute` 提交即失败，治理永不触发**——开发者无法在本地验证治理功能，"日常路径不治理"成立。

目标：给 `/execute` 加同步治理回退，使其在 broker 不可用时仍能在进程内执行 pipeline + 治理闭环，达成"主路径触发治理闭环"完成条件。本次仅做 Gap 1（主路径 + 对应测试），集成层假绿下轮处理。

## 策略（已与用户确认）

**异步优先 + 同步回退**：prod（Redis 在线）走 `delay()` 保持异步扩展性；捕获 broker 不可用异常时自动降级为进程内同步执行 pipeline+治理。dev 无需 Redis 即可触发治理。

## 方案：`run_test_pipeline.apply()` 同步回退（非提取）

**不提取 executor 模块**，而是用 Celery 官方 eager 执行 API `Task.apply()`。

### 为什么用 apply() 而非提取 executor.py

- **零改动 tasks.py**：tasks.py 已修复成走 GovernanceOrchestrator（`tasks.py:6,63`），且 `tests/worker/test_tasks.py`（17 测试，变异验证 4/4 捕获）+ `tests/exposed_bugs/test_bug_governance_not_in_main_path.py`（回归网）都依赖 tasks.py 现有结构。提取会破坏这些刚收敛的测试。
- **单一真相源更强**：apply() 在进程内运行**任务体本身**，同步/异步路径走完全相同代码。提取反而引入两个调用点可能发散。
- **apply() 不依赖 broker**：Celery 文档明确的本地 eager 执行，返回内存 EagerResult，无需 Redis/Mongo result backend。
- 真实执行，非 mock——符合"真实严格"。

### 改动 1：`src/platform/api.py` /execute 加同步回退分支

当前（`api.py:1715-1743`）只有 `delay()` + 通用 `except Exception` → `TASK_SUBMISSION_FAILED`。改为三分支：

```python
# 模块级（靠近其他 import）：防御式导入 broker 不可用异常类型
try:
    from kombu.exceptions import OperationalError as _KombuOperationalError
except ImportError:
    _KombuOperationalError = None
try:
    from redis.exceptions import ConnectionError as _RedisConnectionError
except ImportError:
    _RedisConnectionError = None
_BROKER_UNAVAILABLE_EXC = tuple(
    t for t in [_KombuOperationalError, _RedisConnectionError] if t is not None
)
```

`/execute` 端点改为：
```python
@app.post("/execute")
async def execute_pipeline(request: HttpRequest, user: User = Depends(require_permission(Permission.RUN_TEST))):
    import uuid as _uuid
    from fastapi.concurrency import run_in_threadpool
    trace_id = str(_uuid.uuid4())[:8]
    request_dict = request.model_dump(mode="json")
    request_dict["_trace_id"] = trace_id
    request_dict["_requester"] = user.username

    # 异步优先：prod 主路径，Celery 入队
    try:
        task = run_test_pipeline.delay(request_dict)
        return ApiResponse(success=True, data={"status": "queued", "task_id": task.id, "trace_id": trace_id}, message="Pipeline 已入队")
    except _BROKER_UNAVAILABLE_EXC as broker_err:
        # 同步回退：broker 不可用（dev/无 Redis），进程内 eager 执行任务体
        # apply() 运行 run_test_pipeline 任务体本身（pipeline + 失败触发治理闭环），
        # 保证同步/异步走完全相同逻辑。threadpool 包装避免阻塞 async 事件循环
        # （任务体内 AsyncLoopManager + future.result(timeout=60) 会阻塞）。
        logger.warning(f"Celery broker 不可用, 降级同步执行 pipeline+治理: {broker_err}")
        try:
            eager_result = await run_in_threadpool(run_test_pipeline.apply, (request_dict,))
            if eager_result.successful():
                return ApiResponse(success=True,
                    data={"status": "completed_sync", "trace_id": trace_id,
                          "result": eager_result.result, "fallback": "sync"},
                    message="Broker 不可用, 已同步执行 pipeline+治理闭环")
            # 任务体重抛异常（pipeline + 治理均失败）→ 传播
            raise eager_result.result
        except Exception as sync_err:
            logger.error(f"同步执行 pipeline+治理失败: {sync_err}", exc_info=True)
            return ApiResponse(success=False, data={"trace_id": trace_id},
                message=f"同步执行失败: {sync_err}", error_code="EXECUTION_FAILED")
    except Exception as e:
        logger.error(f"Pipeline submission failed: {e}", exc_info=True)
        return ApiResponse(success=False, data={"trace_id": trace_id},
            message=f"任务投递失败: {e}", error_code="TASK_SUBMISSION_FAILED")
```

关键点：
- `except _BROKER_UNAVAILABLE_EXC` 必须在通用 `except Exception` **之前**（specific first）
- `run_in_threadpool` 包装 `apply()`，避免阻塞 FastAPI 事件循环（任务体 `future.result(timeout=60)` 同步阻塞）
- 响应带 `fallback: "sync"` 标记，prod broker 抖动静默走同步时可观测（用户已确认接受该 tradeoff，需明显日志——WARNING 已满足）
- tasks.py **零改动**

### 改动 2：新增测试 `tests/exposed_bugs/test_bug_execute_sync_governance_fallback.py`

三组测试（真实严格，禁止弱断言）：

**TestExecuteAsyncPath**（验证异步优先，不被回退污染）：
- `test_broker_available_returns_queued`：mock `run_test_pipeline.delay` 返回带 `.id` 的假 task → 断言响应 `status=="queued"`、`task_id` 存在、`apply` 未被调用

**TestExecuteSyncFallbackWiring**（验证回退接线）：
- `test_broker_unavailable_triggers_sync_apply`：mock `delay` 抛 `OperationalError`，mock `apply` 返回 `EagerResult(successful=True, result={"status":"PENDING_APPROVAL",...})` → 断言响应 `status=="completed_sync"`、`fallback=="sync"`、`result.status=="PENDING_APPROVAL"`、`apply` 被调用一次
- `test_sync_fallback_propagates_failure_when_governance_also_fails`：mock `delay` 抛异常，mock `apply` 返回 `successful()=False`、`.result=RuntimeError(...)` → 断言响应 `success=False`、`error_code=="EXECUTION_FAILED"`

**TestExecuteSyncFallbackRealGovernance**（真实严格——真跑治理）：
- `test_sync_fallback_actually_triggers_governance_closed_loop`：mock `delay` 抛 `OperationalError`，**不 mock apply**，让 `apply()` 真实运行任务体；mock `ResourceContainer`/`ExecutionPipeline.run`（参照 `test_tasks.py::TestGovernanceCoroutineRealRun` 的 `_run_coro_side_effect` 模式）使 pipeline 失败 → 断言响应 `result` 含 `status` 字段（证明治理闭环真触发，非只返回错误）
- 用 `TestClient(app)` + `auth_headers`（conftest fixture）走真实 HTTP 路径

### 改动 3：扩展变异验证

在 `tests/exposed_bugs/_mutation_verify_tasks.py` 旁新增（或复用模式）变异用例，证明新断言有牙：
- **M5**：删除同步回退分支（broker 异常直落 `TASK_SUBMISSION_FAILED`）→ `test_broker_unavailable_triggers_sync_apply` 必 FAIL
- **M6**：回退分支不调 `apply`（直接返回空成功）→ `test_sync_fallback_actually_triggers_governance_closed_loop` 必 FAIL

## 不改动（明确边界）

- `src/worker/tasks.py`：零改动（保持已收敛的治理逻辑 + 测试稳定）
- `tests/worker/test_tasks.py`：零改动（17 测试 + 变异验证保持有效）
- `tests/exposed_bugs/test_bug_governance_not_in_main_path.py`：零改动（仍作回归网，tasks.py 未变）
- 集成层假绿（test_full_stack_integration 等）：下轮处理

## 验证

1. **新测试单独跑**：`python -m pytest tests/exposed_bugs/test_bug_execute_sync_governance_fallback.py -v` 全绿
2. **变异验证**：M5/M6 被 CAPTURED（测试 FAIL），证明断言有牙
3. **回归**：`python -m pytest tests/worker/ tests/exposed_bugs/ tests/platform/test_api_isolation.py -q` 全绿（确认 /execute 改动未破坏现有平台测试）
4. **手动端到端**（可选）：停 Redis，POST /execute（带 auth）→ 响应 `fallback:"sync"` 且含治理结果；启 Redis → 响应 `status:"queued"`

## 已知限制（诚实声明）

- 同步回退运行任务体，pipeline 依赖 `ResourceContainer`（Mongo）；dev 无 Mongo 时 pipeline 失败 → 治理仍触发（诊断 Mongo 失败），符合"治理闭环可达"目标，但 pipeline 不会成功执行
- `apply()` 的 `self.request.id` 由 Celery eager 生成（非 /execute 的 trace_id）；任务内 trace_id 与 /execute 返回的 trace_id 可能不同——验证步骤需确认 apply() 是否设 request.id，若不设则任务走 None 边界（已测安全）
- prod broker 抖动会静默走同步（阻塞至多 60s）；已用 WARNING 日志 + `fallback:"sync"` 响应标记保证可观测
