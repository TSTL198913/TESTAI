"""
Platform WorkflowEngine测试 - 覆盖五种场景
目标覆盖率≥80%
"""
import pytest
from datetime import datetime

from src.platform.workflow import (
    WorkflowEngine, WorkflowDefinition, WorkflowTask, WorkflowStatus, TaskType
)


class TestWorkflowEngine:
    """WorkflowEngine测试类"""

    # === 正向场景 ===
    def test_define_workflow_returns_id(self):
        """正向：定义工作流返回ID"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(name="Test Workflow", description="Test Description")
        
        workflow_id = engine.define_workflow(workflow_def)
        
        assert workflow_id is not None
        assert len(workflow_id) == 8
        assert engine.get_workflow(workflow_id) == workflow_def

    def test_get_workflow_returns_definition(self):
        """正向：获取工作流定义"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(name="Test Workflow")
        workflow_id = engine.define_workflow(workflow_def)
        
        result = engine.get_workflow(workflow_id)
        
        assert result is not None
        assert result.name == "Test Workflow"

    def test_list_workflows_returns_all(self):
        """正向：列出所有工作流"""
        engine = WorkflowEngine()
        engine.define_workflow(WorkflowDefinition(name="Workflow 1"))
        engine.define_workflow(WorkflowDefinition(name="Workflow 2"))
        
        workflows = engine.list_workflows()
        
        assert len(workflows) == 2
        assert workflows[0]["name"] == "Workflow 1"
        assert workflows[1]["name"] == "Workflow 2"

    @pytest.mark.asyncio
    async def test_execute_workflow_completed(self):
        """正向：执行工作流完成"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="Check Status", params={"action": "get_status"}),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert result["status"] == "completed"
        assert "instance_id" in result
        assert "task_results" in result
        assert "completed_at" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_with_params(self):
        """正向：执行工作流带参数"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="Check Status", params={"action": "get_status"}),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id, params={"env": "test"})
        
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_workflow_with_task_dependencies(self):
        """正向：执行带依赖的工作流"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.MONITORING, name="Task 1", id="task1"),
                WorkflowTask(type=TaskType.MONITORING, name="Task 2", id="task2", depends_on=["task1"]),
                WorkflowTask(type=TaskType.MONITORING, name="Task 3", id="task3", depends_on=["task2"]),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert result["status"] == "completed"
        assert len(result["task_results"]) == 3

    def test_get_workflow_status_returns_status(self):
        """正向：获取工作流实例状态"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[WorkflowTask(type=TaskType.MONITORING, name="Task")],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        import asyncio
        result = asyncio.run(engine.execute_workflow(workflow_id))
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        
        assert status is not None
        assert status["instance_id"] == instance_id
        assert status["workflow_id"] == workflow_id
        assert status["status"] == "completed"

    def test_list_instances_returns_all(self):
        """正向：列出所有工作流实例"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[WorkflowTask(type=TaskType.MONITORING, name="Task")],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        import asyncio
        asyncio.run(engine.execute_workflow(workflow_id))
        asyncio.run(engine.execute_workflow(workflow_id))
        
        instances = engine.list_instances()
        
        assert len(instances) == 2

    def test_list_instances_filtered_by_workflow(self):
        """正向：按工作流过滤实例"""
        engine = WorkflowEngine()
        workflow1 = engine.define_workflow(WorkflowDefinition(name="Workflow 1", tasks=[WorkflowTask(type=TaskType.MONITORING, name="Task")]))
        workflow2 = engine.define_workflow(WorkflowDefinition(name="Workflow 2", tasks=[WorkflowTask(type=TaskType.MONITORING, name="Task")]))
        
        import asyncio
        asyncio.run(engine.execute_workflow(workflow1))
        asyncio.run(engine.execute_workflow(workflow1))
        asyncio.run(engine.execute_workflow(workflow2))
        
        instances1 = engine.list_instances(workflow_id=workflow1)
        instances2 = engine.list_instances(workflow_id=workflow2)
        
        assert len(instances1) == 2
        assert len(instances2) == 1

    def test_calculate_execution_order_no_dependencies(self):
        """正向：计算无依赖任务的执行顺序"""
        engine = WorkflowEngine()
        tasks = [
            WorkflowTask(type=TaskType.MONITORING, name="Task 1", id="task1"),
            WorkflowTask(type=TaskType.MONITORING, name="Task 2", id="task2"),
            WorkflowTask(type=TaskType.MONITORING, name="Task 3", id="task3"),
        ]
        
        order = engine._calculate_execution_order(tasks)
        
        assert len(order) == 3
        assert "task1" in order
        assert "task2" in order
        assert "task3" in order

    def test_calculate_execution_order_with_dependencies(self):
        """正向：计算带依赖任务的执行顺序"""
        engine = WorkflowEngine()
        tasks = [
            WorkflowTask(type=TaskType.MONITORING, name="Task 1", id="task1"),
            WorkflowTask(type=TaskType.MONITORING, name="Task 2", id="task2", depends_on=["task1"]),
            WorkflowTask(type=TaskType.MONITORING, name="Task 3", id="task3", depends_on=["task2"]),
        ]
        
        order = engine._calculate_execution_order(tasks)
        
        assert len(order) == 3
        assert order.index("task1") < order.index("task2")
        assert order.index("task2") < order.index("task3")

    # === 负向场景 ===
    def test_get_workflow_nonexistent(self):
        """负向：获取不存在的工作流"""
        engine = WorkflowEngine()
        result = engine.get_workflow("nonexistent")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_nonexistent_workflow(self):
        """负向：执行不存在的工作流"""
        engine = WorkflowEngine()
        
        result = await engine.execute_workflow("nonexistent")
        
        assert result["status"] == "failed"
        assert result["error"] == "Workflow not found"

    def test_get_workflow_status_nonexistent(self):
        """负向：获取不存在的工作流实例状态"""
        engine = WorkflowEngine()
        result = engine.get_workflow_status("nonexistent")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_workflow_with_unknown_task_type(self):
        """负向：执行包含未知任务类型的工作流"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type="unknown_type", name="Unknown Task"),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert result["status"] == "completed"

    # === 边界场景 ===
    def test_define_empty_workflow(self):
        """边界：定义空工作流"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(name="Empty Workflow")
        
        workflow_id = engine.define_workflow(workflow_def)
        
        assert workflow_id is not None
        assert len(engine.list_workflows()) == 1

    @pytest.mark.asyncio
    async def test_execute_empty_workflow(self):
        """边界：执行空工作流"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(name="Empty Workflow")
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert result["status"] == "completed"
        assert len(result["task_results"]) == 0

    def test_calculate_execution_order_cyclic_dependencies(self):
        """边界：循环依赖"""
        engine = WorkflowEngine()
        tasks = [
            WorkflowTask(type=TaskType.MONITORING, name="Task 1", id="task1", depends_on=["task2"]),
            WorkflowTask(type=TaskType.MONITORING, name="Task 2", id="task2", depends_on=["task1"]),
        ]
        
        order = engine._calculate_execution_order(tasks)
        
        assert len(order) == 0

    def test_calculate_execution_order_empty_tasks(self):
        """边界：空任务列表"""
        engine = WorkflowEngine()
        order = engine._calculate_execution_order([])
        
        assert order == []

    # === 异常场景 ===
    @pytest.mark.asyncio
    async def test_execute_workflow_task_exception(self):
        """异常：任务执行异常"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(
            name="Test Workflow",
            tasks=[
                WorkflowTask(type=TaskType.GOVERNANCE, name="Governance Task", params={}),
            ],
        )
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert "status" in result

    # === 依赖场景 ===
    def test_workflow_task_default_values(self):
        """依赖：任务默认值"""
        task = WorkflowTask(type=TaskType.MONITORING, name="Test Task")
        
        assert task.id is not None
        assert len(task.id) == 8
        assert task.params == {}
        assert task.depends_on == []
        assert task.timeout == 60

    def test_workflow_definition_default_values(self):
        """依赖：工作流定义默认值"""
        workflow = WorkflowDefinition(name="Test Workflow")
        
        assert workflow.description == ""
        assert workflow.tasks == []
        assert workflow.triggers == {}

    def test_workflow_status_enum_values(self):
        """依赖：工作流状态枚举值"""
        assert WorkflowStatus.DEFINED.value == "defined"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.PAUSED.value == "paused"

    def test_task_type_enum_values(self):
        """依赖：任务类型枚举值"""
        assert TaskType.GOVERNANCE.value == "governance"
        assert TaskType.MUTATION_TEST.value == "mutation_test"
        assert TaskType.APPROVAL.value == "approval"
        assert TaskType.MONITORING.value == "monitoring"
        assert TaskType.API_TEST.value == "api_test"
        assert TaskType.DELAY.value == "delay"
        assert TaskType.CONDITIONAL.value == "conditional"

    @pytest.mark.asyncio
    async def test_execute_workflow_task_not_found(self):
        """异常：任务不存在"""
        engine = WorkflowEngine()
        workflow_def = WorkflowDefinition(name="Test Workflow", tasks=[])
        workflow_id = engine.define_workflow(workflow_def)
        
        result = await engine.execute_workflow(workflow_id)
        
        assert result["status"] == "completed"
        assert len(result["task_results"]) == 0

    @pytest.mark.asyncio
    async def test_handle_mutation_test_task(self):
        """正向：处理变异测试任务"""
        from unittest.mock import patch, MagicMock
        
        with patch("tests.utils.custom_mutation_test.CustomMutationTester") as mock_tester_cls:
            mock_tester = MagicMock()
            mock_tester.run.return_value = {"kill_rate": 0.8}
            mock_tester_cls.return_value = mock_tester
            
            engine = WorkflowEngine()
            task = WorkflowTask(type=TaskType.MUTATION_TEST, name="Mutation Test", params={"target_dir": "src/governance/"})
            
            result = await engine._handle_mutation_test_task(task, {}, {})
            
            assert "status" in result
            assert result["status"] == "completed"
            assert "report" in result

    @pytest.mark.asyncio
    async def test_handle_approval_task_approve(self):
        """正向：处理审批任务-批准"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.APPROVAL, name="Approval", params={"tx_id": "test_tx", "action": "approve", "approver": "admin"})
        
        result = await engine._handle_approval_task(task, {}, {})
        
        assert "status" in result
        assert "approved" in result
        assert "action" in result
        assert result["action"] == "approve"

    @pytest.mark.asyncio
    async def test_handle_approval_task_reject(self):
        """正向：处理审批任务-拒绝"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.APPROVAL, name="Approval", params={"tx_id": "test_tx", "action": "reject", "approver": "admin", "reason": "Not approved"})
        
        result = await engine._handle_approval_task(task, {}, {})
        
        assert "status" in result
        assert "approved" in result
        assert "action" in result
        assert result["action"] == "reject"

    @pytest.mark.asyncio
    async def test_handle_approval_task_unknown_action(self):
        """负向：处理审批任务-未知操作"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.APPROVAL, name="Approval", params={"tx_id": "test_tx", "action": "unknown"})
        
        result = await engine._handle_approval_task(task, {}, {})
        
        assert result["approved"] == False

    @pytest.mark.asyncio
    async def test_handle_monitoring_task_get_status(self):
        """正向：处理监控任务-获取状态"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.MONITORING, name="Monitor", params={"action": "get_status"})
        
        result = await engine._handle_monitoring_task(task, {}, {})
        
        assert result["status"] == "completed"
        assert "health_status" in result

    @pytest.mark.asyncio
    async def test_handle_monitoring_task_record_metrics(self):
        """正向：处理监控任务-记录指标"""
        from unittest.mock import patch, MagicMock
        
        with patch("src.governance.monitoring.HealthMonitor") as mock_health:
            mock_health_instance = MagicMock()
            mock_health.return_value = mock_health_instance
            mock_health_instance.record_diagnosis_success.return_value = None
            
            engine = WorkflowEngine()
            task = WorkflowTask(type=TaskType.MONITORING, name="Monitor", params={"action": "record_metrics"})
            
            result = await engine._handle_monitoring_task(task, {}, {})
            
            assert result["status"] == "completed"
            assert result["action"] == "metrics_recorded"

    @pytest.mark.asyncio
    async def test_handle_monitoring_task_create_alert(self):
        """正向：处理监控任务-创建告警"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.MONITORING, name="Monitor", params={"action": "create_alert", "level": "ERROR", "message": "Test alert"})
        
        result = await engine._handle_monitoring_task(task, {}, {})
        
        assert result["status"] == "completed"
        assert result["action"] == "alert_created"

    @pytest.mark.asyncio
    async def test_handle_monitoring_task_unknown_action(self):
        """负向：处理监控任务-未知操作"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.MONITORING, name="Monitor", params={"action": "unknown"})
        
        result = await engine._handle_monitoring_task(task, {}, {})
        
        assert result["status"] == "completed"
        assert result["action"] == "unknown"

    @pytest.mark.asyncio
    async def test_handle_delay_task(self):
        """正向：处理延迟任务"""
        engine = WorkflowEngine()
        task = WorkflowTask(type=TaskType.DELAY, name="Delay", params={"seconds": 0.01})
        
        result = await engine._handle_delay_task(task, {}, {})
        
        assert result["status"] == "completed"
        assert result["delayed_seconds"] == 0.01
