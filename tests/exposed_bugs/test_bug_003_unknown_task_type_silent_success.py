"""BUG-003: 未知任务类型静默成功。

源码位置:
- src/platform/workflow.py:33-61 WorkflowTask(@dataclass,type 字段不校验枚举)
- src/platform/workflow.py:230-235 _register_default_handlers(只注册 5 个 handler)
- src/platform/workflow.py:377-382 _execute_task(handler 缺失返回 skipped)

根因:
1. WorkflowTask 是 @dataclass 而非 Pydantic 模型,type 字段不强制校验枚举
2. _register_default_handlers 只注册 GOVERNANCE/MUTATION_TEST/APPROVAL/MONITORING/DELAY
3. API_TEST 和 CONDITIONAL 是合法 TaskType 枚举但无 handler
4. _execute_task 在 handler 缺失时返回 {"status": "skipped"},execute_workflow 仍 COMPLETED
5. 违反用户规则"禁止使用弱类型的隐式转换"

现有测试反模式:tests/platform/test_workflow.py:217-230
- assert result["status"] == "completed" 把 bug 当 expected behavior 固化
"""
import pytest

from src.platform.workflow import (
    WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType
)


@pytest.mark.asyncio
async def test_unknown_task_type_string_fails_workflow():
    """WorkflowTask.type 为完全无效的字符串时,工作流应 failed。"""
    engine = WorkflowEngine()
    wf = WorkflowDefinition(
        name="bad_task_type_str",
        tasks=[
            WorkflowTask(type="completely_invalid_type", name="bad"),
        ],
    )
    wf_id = engine.define_workflow(wf)

    result = await engine.execute_workflow(wf_id)

    assert result["status"] == "failed", (
        f"未知任务类型应 failed,实际: {result['status']}, "
        f"task_results: {result.get('task_results')}"
    )


@pytest.mark.asyncio
async def test_unregistered_enum_task_type_fails():
    """合法 TaskType 枚举但未注册 handler 也应 failed。"""
    engine = WorkflowEngine()
    failures = []

    for task_type in (TaskType.API_TEST, TaskType.CONDITIONAL):
        wf = WorkflowDefinition(
            name=f"test_unregistered_{task_type.value}",
            tasks=[WorkflowTask(type=task_type, name="x")],
        )
        wf_id = engine.define_workflow(wf)
        result = await engine.execute_workflow(wf_id)
        if result["status"] != "failed":
            failures.append(
                f"{task_type.value}: expected failed, got {result['status']}"
            )

    assert not failures, (
        "API_TEST 和 CONDITIONAL 应 failed(无 handler): " + "; ".join(failures)
    )


@pytest.mark.asyncio
async def test_unknown_task_type_task_result_indicates_failure():
    """未知任务类型时,工作流 status 应 failed。"""
    engine = WorkflowEngine()
    wf = WorkflowDefinition(
        name="bad_task_type_check",
        tasks=[
            WorkflowTask(type="another_invalid_type", name="bad", id="bad_task"),
        ],
    )
    wf_id = engine.define_workflow(wf)

    result = await engine.execute_workflow(wf_id)

    assert result["status"] == "failed", (
        f"包含未知任务类型的工作流应 failed, 实际: {result['status']}"
    )
