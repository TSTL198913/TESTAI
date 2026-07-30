"""BUG-002: 循环依赖静默成功。

源码位置:src/platform/workflow.py:360-375 _calculate_execution_order + L295-334 execute_workflow

根因:
1. _calculate_execution_order 用 Kahn 算法,循环依赖时返回空列表 []
2. execute_workflow 遍历空列表,跳过所有任务
3. 仍设置 instance.status = WorkflowStatus.COMPLETED,返回 status="completed"

正确行为:循环依赖应检测并返回 failed,错误信息含 cyclic/circular。

现有测试反模式:tests/platform/test_workflow.py:256-266
- 只断言 len(order) == 0,把"循环依赖静默丢弃"当成 expected behavior
- 没测试 execute_workflow 在循环依赖下应返回 failed
"""
import pytest

from src.platform.workflow import (
    WorkflowEngine, WorkflowDefinition, WorkflowTask, WorkflowStatus, TaskType
)


@pytest.mark.asyncio
async def test_cyclic_dependency_fails_workflow():
    """循环依赖工作流应返回 failed,而非静默 completed。

    正确行为:检测到循环依赖时,status="failed",error 含 cyclic/circular 关键词。
    """
    engine = WorkflowEngine()
    wf = WorkflowDefinition(
        name="cyclic_test",
        tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="t1", id="t1", depends_on=["t2"]),
            WorkflowTask(type=TaskType.MONITORING, name="t2", id="t2", depends_on=["t1"]),
        ],
    )
    wf_id = engine.define_workflow(wf)

    result = await engine.execute_workflow(wf_id)

    assert result["status"] == "failed", (
        f"循环依赖应失败,当前实现静默返回 completed, 实际 status={result['status']}, "
        f"task_results={result.get('task_results')}"
    )
    error_msg = result.get("error", "").lower()
    assert "cyclic" in error_msg or "circular" in error_msg, (
        f"错误信息应包含 cyclic/circular 关键词,实际 error: {result.get('error')}"
    )


@pytest.mark.asyncio
async def test_cyclic_dependency_instance_status_is_failed():
    """循环依赖时 WorkflowInstance.status 必须是 FAILED,而非 COMPLETED。"""
    engine = WorkflowEngine()
    wf = WorkflowDefinition(
        name="cyclic_test_2",
        tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="t1", id="t1", depends_on=["t2"]),
            WorkflowTask(type=TaskType.MONITORING, name="t2", id="t2", depends_on=["t1"]),
        ],
    )
    wf_id = engine.define_workflow(wf)

    result = await engine.execute_workflow(wf_id)
    instance_id = result.get("instance_id")

    instance = engine.instances.get(instance_id)
    assert instance is not None, "instance 必须存在"
    assert instance.status == WorkflowStatus.FAILED, (
        f"instance.status 必须是 FAILED,实际: {instance.status}"
    )


@pytest.mark.asyncio
async def test_cyclic_dependency_task_results_empty_indicates_failure():
    """循环依赖时 task_results 为空,应明确失败,而非 completed。"""
    engine = WorkflowEngine()
    wf = WorkflowDefinition(
        name="cyclic_test_3",
        tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="t1", id="t1", depends_on=["t2"]),
            WorkflowTask(type=TaskType.MONITORING, name="t2", id="t2", depends_on=["t1"]),
        ],
    )
    wf_id = engine.define_workflow(wf)

    result = await engine.execute_workflow(wf_id)

    # 循环依赖 → 0 个任务执行 → task_results 为空
    # 但 status 必须是 failed(因为工作流定义有任务却没执行任何任务)
    assert len(result["task_results"]) == 0, "循环依赖时不应执行任何任务"
    assert result["status"] == "failed", (
        f"循环依赖 + 0 任务执行,应明确 failed,而非 completed, 实际: {result['status']}"
    )
