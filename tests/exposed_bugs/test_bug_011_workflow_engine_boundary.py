"""BUG-011: WorkflowEngine 任务执行边界条件缺失。

源码位置: src/platform/workflow.py:139-607 WorkflowEngine

根因:
1. execute_workflow 中 tasks 为空列表时仍创建实例并标记 completed
2. _calculate_execution_order 对空 tasks 未做特殊处理
3. _execute_task 对未知任务类型只返回 skipped,无日志记录
4. list_workflows 可能返回空列表时无警告
"""
import pytest
import asyncio

from src.platform.workflow import (
    WorkflowEngine,
    WorkflowDefinition,
    WorkflowTask,
    TaskType,
    WorkflowStatus,
)


@pytest.fixture
def fresh_engine():
    """创建干净的 WorkflowEngine 实例。"""
    engine = WorkflowEngine()
    engine.workflows = {}
    engine.instances = {}
    return engine


def test_workflow_with_empty_tasks_should_fail(fresh_engine):
    """无任务的工作流定义应抛出 ValueError。"""
    empty_workflow = WorkflowDefinition(
        name="空工作流",
        description="无任务",
        tasks=[],
    )
    
    with pytest.raises(ValueError, match="工作流必须包含至少一个任务"):
        fresh_engine.define_workflow(empty_workflow)


@pytest.mark.asyncio
async def test_execute_empty_workflow_returns_failed(fresh_engine):
    """执行无任务工作流应在定义阶段就失败。"""
    empty_workflow = WorkflowDefinition(
        name="空工作流",
        description="无任务",
        tasks=[],
    )
    
    with pytest.raises(ValueError, match="工作流必须包含至少一个任务"):
        fresh_engine.define_workflow(empty_workflow)


@pytest.mark.asyncio
async def test_unknown_task_type_logs_warning(caplog, fresh_engine):
    """执行未注册处理器的任务类型时应记录 ERROR 级别日志并抛出异常。"""
    import logging
    caplog.set_level(logging.ERROR)
    
    workflow = WorkflowDefinition(
        name="测试工作流",
        description="包含未注册处理器的任务",
        tasks=[
            WorkflowTask(
                type=TaskType.API_TEST,
                name="API测试任务",
                params={},
            ),
        ],
    )
    
    workflow_id = fresh_engine.define_workflow(workflow)
    
    result = await fresh_engine.execute_workflow(workflow_id, {})
    
    assert result.get("status") == "failed", (
        f"未注册处理器的任务类型应导致工作流失败,实际: {result}"
    )
    assert any("api_test" in record.message.lower() for record in caplog.records), (
        f"执行未知任务类型时应记录 ERROR 日志,实际日志: {[r.message for r in caplog.records]}"
    )


def test_duplicate_workflow_name_rejected(fresh_engine):
    """重复名称的工作流定义应抛出 ValueError。"""
    workflow1 = WorkflowDefinition(
        name="重复名称",
        description="工作流1",
        tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="任务1", params={}),
        ],
    )
    
    workflow2 = WorkflowDefinition(
        name="重复名称",
        description="工作流2",
        tasks=[
            WorkflowTask(type=TaskType.MONITORING, name="任务1", params={}),
        ],
    )
    
    fresh_engine.define_workflow(workflow1)
    
    with pytest.raises(ValueError, match="已存在"):
        fresh_engine.define_workflow(workflow2)