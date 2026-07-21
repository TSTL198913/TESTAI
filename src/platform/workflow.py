import uuid
import os
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    DEFINED = "defined"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class TaskType(str, Enum):
    GOVERNANCE = "governance"
    MUTATION_TEST = "mutation_test"
    APPROVAL = "approval"
    MONITORING = "monitoring"
    API_TEST = "api_test"
    DELAY = "delay"
    CONDITIONAL = "conditional"


@dataclass
class WorkflowTask:
    type: TaskType
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    timeout: int = 60

    def to_dict(self):
        return {
            "type": self.type.value,
            "name": self.name,
            "id": self.id,
            "params": self.params,
            "depends_on": self.depends_on,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            type=TaskType(data["type"]),
            name=data["name"],
            id=data.get("id", str(uuid.uuid4())[:8]),
            params=data.get("params", {}),
            depends_on=data.get("depends_on", []),
            timeout=data.get("timeout", 60),
        )


@dataclass
class WorkflowDefinition:
    name: str
    description: str = ""
    tasks: List[WorkflowTask] = field(default_factory=list)
    triggers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "triggers": self.triggers,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            tasks=[WorkflowTask.from_dict(t) for t in data.get("tasks", [])],
            triggers=data.get("triggers", {}),
        )


@dataclass
class WorkflowInstance:
    workflow_id: str
    instance_id: str
    status: WorkflowStatus
    tasks: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowEngine:
    def __init__(self):
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.instances: Dict[str, WorkflowInstance] = {}
        self._task_handlers: Dict[TaskType, Callable] = {}
        self._use_database = bool(os.environ.get("DATABASE_URL"))
        self._db = None
        if self._use_database:
            try:
                from src.storage.database import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"Database not available, using memory: {e}")
                self._use_database = False
        self._load_workflows()
        self._register_default_handlers()

    def _load_workflows(self):
        if self._use_database and self._db:
            try:
                rows = self._db.select_all(self._db.workflows_table)
                for row in rows:
                    self.workflows[row["workflow_id"]] = WorkflowDefinition.from_dict({
                        "name": row["name"],
                        "description": row.get("description", ""),
                        "tasks": row.get("tasks", []),
                        "triggers": row.get("triggers", {}),
                    })
                rows = self._db.select_all(self._db.workflow_instances_table)
                for row in rows:
                    self.instances[row["instance_id"]] = WorkflowInstance(
                        workflow_id=row["workflow_id"],
                        instance_id=row["instance_id"],
                        status=WorkflowStatus(row["status"]),
                        tasks=row.get("tasks", {}),
                        created_at=row.get("created_at", datetime.now()),
                        started_at=row.get("started_at"),
                        completed_at=row.get("completed_at"),
                        error=row.get("error"),
                    )
            except Exception as e:
                logger.warning(f"Database load failed: {e}")

    def _register_default_handlers(self):
        self._task_handlers[TaskType.GOVERNANCE] = self._handle_governance_task
        self._task_handlers[TaskType.MUTATION_TEST] = self._handle_mutation_test_task
        self._task_handlers[TaskType.APPROVAL] = self._handle_approval_task
        self._task_handlers[TaskType.MONITORING] = self._handle_monitoring_task
        self._task_handlers[TaskType.DELAY] = self._handle_delay_task

    def define_workflow(self, definition: WorkflowDefinition) -> str:
        workflow_id = str(uuid.uuid4())[:8]
        self.workflows[workflow_id] = definition

        if self._use_database and self._db:
            self._db.insert_one(self._db.workflows_table, {
                "workflow_id": workflow_id,
                "name": definition.name,
                "description": definition.description,
                "tasks": definition.to_dict()["tasks"],
                "triggers": definition.triggers,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            })
        return workflow_id

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self.workflows.get(workflow_id)

    async def execute_workflow(self, workflow_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        definition = self.get_workflow(workflow_id)
        if not definition:
            return {"status": "failed", "error": "Workflow not found"}

        instance_id = str(uuid.uuid4())[:8]
        instance = WorkflowInstance(
            workflow_id=workflow_id,
            instance_id=instance_id,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(),
        )
        self.instances[instance_id] = instance

        if self._use_database and self._db:
            self._db.insert_one(self._db.workflow_instances_table, {
                "instance_id": instance_id,
                "workflow_id": workflow_id,
                "status": instance.status.value,
                "tasks": {},
                "created_at": instance.created_at,
                "started_at": instance.started_at,
            })

        task_results = {}
        try:
            execution_order = self._calculate_execution_order(definition.tasks)

            for task_id in execution_order:
                task = next((t for t in definition.tasks if t.id == task_id), None)
                if not task:
                    continue

                task_results[task_id] = await self._execute_task(task, params, task_results)
                instance.tasks[task_id] = {
                    "status": "completed",
                    "result": task_results[task_id],
                }

            instance.status = WorkflowStatus.COMPLETED
            instance.completed_at = datetime.now()

            if self._use_database and self._db:
                self._db.update_many(
                    self._db.workflow_instances_table,
                    self._db.workflow_instances_table.c.instance_id == instance_id,
                    {
                        "status": instance.status.value,
                        "tasks": instance.tasks,
                        "completed_at": instance.completed_at,
                    },
                )

            return {
                "status": "completed",
                "instance_id": instance_id,
                "task_results": task_results,
                "completed_at": instance.completed_at.isoformat(),
            }

        except Exception as e:
            instance.status = WorkflowStatus.FAILED
            instance.error = str(e)
            instance.completed_at = datetime.now()

            if self._use_database and self._db:
                self._db.update_many(
                    self._db.workflow_instances_table,
                    self._db.workflow_instances_table.c.instance_id == instance_id,
                    {
                        "status": instance.status.value,
                        "error": instance.error,
                        "completed_at": instance.completed_at,
                    },
                )

            return {
                "status": "failed",
                "instance_id": instance_id,
                "error": str(e),
                "task_results": task_results,
            }

    def _calculate_execution_order(self, tasks: List[WorkflowTask]) -> List[str]:
        in_degree = {task.id: len(task.depends_on) for task in tasks}
        queue = [task.id for task in tasks if len(task.depends_on) == 0]
        order = []

        while queue:
            task_id = queue.pop(0)
            order.append(task_id)

            for task in tasks:
                if task_id in task.depends_on:
                    in_degree[task.id] -= 1
                    if in_degree[task.id] == 0:
                        queue.append(task.id)

        return order

    async def _execute_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._task_handlers.get(task.type)
        if not handler:
            return {"status": "skipped", "reason": f"No handler for task type {task.type}"}

        return await handler(task, params, prev_results)

    async def _handle_governance_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.governance.orchestrator import GovernanceOrchestrator
        from src.governance.models import DiagnosticContext

        orchestrator = GovernanceOrchestrator()
        context = DiagnosticContext(
            component_name=task.params.get("component_name", "default"),
            step_id=task.params.get("step_id", str(uuid.uuid4())[:8]),
            input_data=task.params.get("input_data", {}),
            actual_output=task.params.get("actual_output", ""),
            expected_baseline=task.params.get("expected_baseline", ""),
        )
        result = await orchestrator.execute_governance_flow(context)
        return {"status": result.get("status"), "result": result}

    async def _handle_mutation_test_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from tests.utils.custom_mutation_test import CustomMutationTester

        target_dir = task.params.get("target_dir", "src/governance/")
        tester = CustomMutationTester(target_dir=target_dir)
        report = tester.run()
        return {"status": "completed", "report": report}

    async def _handle_approval_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.governance.approval import ApprovalManager

        manager = ApprovalManager()
        tx_id = task.params.get("tx_id")
        action = task.params.get("action", "approve")
        approver = task.params.get("approver", "system")

        if action == "approve":
            result = manager.approve(tx_id, approver)
        elif action == "reject":
            result = manager.reject(tx_id, approver, task.params.get("reason", ""))
        else:
            result = False

        return {"status": "completed", "approved": result, "action": action}

    async def _handle_monitoring_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.governance.monitoring import HealthMonitor, AlertManager

        health_monitor = HealthMonitor()
        alert_manager = AlertManager()

        action = task.params.get("action", "get_status")
        if action == "get_status":
            status = health_monitor.get_health_status()
            return {"status": "completed", "health_status": status}
        elif action == "record_metrics":
            health_monitor.record_diagnosis_success()
            return {"status": "completed", "action": "metrics_recorded"}
        elif action == "create_alert":
            alert_manager.create_alert(
                level=task.params.get("level", "INFO"),
                message=task.params.get("message", ""),
                component=task.params.get("component", "workflow"),
            )
            return {"status": "completed", "action": "alert_created"}

        return {"status": "completed", "action": action}

    async def _handle_delay_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        import asyncio

        delay_seconds = task.params.get("seconds", 10)
        await asyncio.sleep(delay_seconds)
        return {"status": "completed", "delayed_seconds": delay_seconds}

    def get_workflow_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        instance = self.instances.get(instance_id)
        if not instance:
            return None

        return {
            "instance_id": instance.instance_id,
            "workflow_id": instance.workflow_id,
            "status": instance.status.value,
            "created_at": instance.created_at.isoformat(),
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "error": instance.error,
            "tasks": instance.tasks,
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        return [
            {"id": wid, "name": w.name, "description": w.description, "task_count": len(w.tasks)}
            for wid, w in self.workflows.items()
        ]

    def list_instances(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        instances = self.instances.values()
        if workflow_id:
            instances = [i for i in instances if i.workflow_id == workflow_id]

        return [
            {
                "instance_id": i.instance_id,
                "workflow_id": i.workflow_id,
                "status": i.status.value,
                "created_at": i.created_at.isoformat(),
            }
            for i in instances
        ]