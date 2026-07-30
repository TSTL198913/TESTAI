import uuid
import os
import logging
import re
import threading
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pydantic import BaseModel, field_validator, ValidationError

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
    AI_EVALUATE = "ai_evaluate"
    AI_CLASSIFY = "ai_classify"
    AI_QA = "ai_qa"


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


class WorkflowDefinition(BaseModel):
    name: str
    description: str = ""
    tasks: List["WorkflowTask"] = []
    triggers: Dict[str, Any] = {}
    task_count: Optional[int] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):  # pylint: disable=no-self-argument
        if not v or not v.strip():
            raise ValueError("工作流名称不能为空")
        if len(v.strip()) > 100:
            raise ValueError("工作流名称不能超过100个字符")
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r"' OR '1'='1",
            r'";?.*DROP TABLE',
            r"\.\./",
            r"SELECT.*FROM",
            r"UNION.*SELECT",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("工作流名称包含非法字符")
        return v.strip()

    @field_validator('task_count')
    @classmethod
    def validate_task_count(cls, v):  # pylint: disable=no-self-argument
        if v is not None:
            if not isinstance(v, int):
                raise ValueError("任务数必须为整数")
            if v < 1:
                raise ValueError("任务数必须大于0")
            if v > 1000:
                raise ValueError("任务数不能超过1000")
        return v

    @field_validator('description')
    @classmethod
    def validate_description(cls, v):  # pylint: disable=no-self-argument
        if v and len(v) > 1000:
            raise ValueError("工作流描述不能超过1000个字符")
        return v

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "triggers": self.triggers,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        tasks = [WorkflowTask.from_dict(t) for t in data.get("tasks", [])]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            tasks=tasks,
            triggers=data.get("triggers", {}),
            task_count=data.get("task_count"),
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
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:  # pylint: disable=access-member-before-definition
            return
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.instances: Dict[str, WorkflowInstance] = {}
        self._task_handlers: Dict[TaskType, Callable] = {}
        self._use_database = bool(os.environ.get("DATABASE_URL"))
        self._db = None
        self._lock = threading.Lock()
        if self._use_database:
            try:
                from src.storage.database import get_db_manager
                self._db = get_db_manager()
            except Exception as e:
                logger.warning(f"Database not available, using memory: {e}")
                self._use_database = False
        with self._lock:
            self._load_workflows()
            self._register_default_handlers()
            self._initialize_default_workflows()
        self._initialized = True

    def _initialize_default_workflows(self):
        if len(self.workflows) == 0:
            test_workflow = WorkflowDefinition(
                name="测试用例生成流程",
                description="基于AI的测试用例自动生成",
                tasks=[
                    WorkflowTask(
                        type=TaskType.GOVERNANCE,
                        name="代码分析",
                        params={"component_name": "code_analyzer"},
                    ),
                    WorkflowTask(
                        type=TaskType.MUTATION_TEST,
                        name="变异测试",
                        params={},
                    ),
                    WorkflowTask(
                        type=TaskType.MONITORING,
                        name="结果分析",
                        params={"action": "record_metrics"},
                    ),
                ],
            )
            self.workflows["wf-001"] = test_workflow

            report_workflow = WorkflowDefinition(
                name="质量报告生成",
                description="自动化测试报告生成与分析",
                tasks=[
                    WorkflowTask(
                        type=TaskType.GOVERNANCE,
                        name="数据收集",
                        params={"component_name": "data_collector"},
                    ),
                    WorkflowTask(
                        type=TaskType.MONITORING,
                        name="报告生成",
                        params={"action": "create_alert", "level": "INFO"},
                    ),
                ],
            )
            self.workflows["wf-002"] = report_workflow

            ai_workflow = WorkflowDefinition(
                name="AI智能分析流程",
                description="集成AI评估、分类和问答的智能分析工作流",
                tasks=[
                    WorkflowTask(
                        type=TaskType.AI_EVALUATE,
                        name="输出评估",
                        params={
                            "output": "Hello World",
                            "expected": "Hello World",
                        },
                    ),
                    WorkflowTask(
                        type=TaskType.AI_CLASSIFY,
                        name="结果分类",
                        params={"text": "AssertionError: expected 5 but got 3"},
                        depends_on=["output_evaluation"],
                    ),
                    WorkflowTask(
                        type=TaskType.AI_QA,
                        name="智能问答",
                        params={"question": "什么是变异测试？"},
                    ),
                ],
            )
            self.workflows["wf-003"] = ai_workflow

            logger.info("Initialized default workflows")

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
        self._task_handlers[TaskType.AI_EVALUATE] = self._handle_ai_evaluate_task
        self._task_handlers[TaskType.AI_CLASSIFY] = self._handle_ai_classify_task
        self._task_handlers[TaskType.AI_QA] = self._handle_ai_qa_task

    def define_workflow(self, definition: WorkflowDefinition) -> str:
        try:
            if isinstance(definition, dict):
                definition = WorkflowDefinition(**definition)
            elif not isinstance(definition, WorkflowDefinition):
                raise ValueError("Invalid workflow definition type")
            
            if not definition.tasks:
                raise ValueError("工作流必须包含至少一个任务")
            
            with self._lock:
                for wid, w in self.workflows.items():
                    if w.name == definition.name:
                        raise ValueError(f"工作流名称 '{definition.name}' 已存在")
                
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
        except ValidationError as e:
            errors = []
            for err in e.errors():
                errors.append(f"{err['loc'][0]}: {err['msg']}")
            raise ValueError("; ".join(errors))
        except Exception as e:
            raise ValueError(str(e))

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        with self._lock:
            return self.workflows.get(workflow_id)

    async def execute_workflow(self, workflow_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        definition = self.get_workflow(workflow_id)
        if not definition:
            return {"status": "failed", "error": "Workflow not found"}

        with self._lock:
            for instance in self.instances.values():
                if instance.workflow_id == workflow_id and instance.status == WorkflowStatus.RUNNING:
                    return {"status": "failed", "error": "Workflow is already running"}

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

        task_results: Dict[str, Dict[str, Any]] = {}
        try:
            execution_order = self._calculate_execution_order(definition.tasks)

            for task_id in execution_order:
                task = next((t for t in definition.tasks if t.id == task_id), None)
                if not task:
                    continue

                task_results[task_id] = await self._execute_task(task, params or {}, task_results)
                with self._lock:
                    instance.tasks[task_id] = {
                        "status": "completed",
                        "result": task_results[task_id],
                    }

            with self._lock:
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
            with self._lock:
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

        # BE-017 修复：检测循环依赖，避免死循环和静默丢弃任务
        if len(order) != len(tasks):
            remaining = [t.id for t in tasks if t.id not in order]
            raise ValueError(
                f"Circular dependency detected among tasks: {remaining}. "
                f"Resolved order has {len(order)} tasks but expected {len(tasks)}."
            )

        return order

    async def _execute_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._task_handlers.get(task.type)
        if not handler:
            logger.error(f"No handler registered for task type: {task.type}, task name: {task.name}")
            raise ValueError(f"No handler registered for task type: {task.type}")

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
        """P1-4 修复:基于真实测试执行计算 kill_rate,弃用 random.random() 造假。

        流程:
        1. 遍历 target_dir 下的 .py 文件,提取 AST 变异点
        2. 对每个变异点,生成变异代码并写入临时文件
        3. 运行 pytest 对应测试文件(subprocess 隔离)
        4. 测试失败 → killed=True(变异被检测到)
        5. 测试通过 → killed=False(变异存活)
        6. kill_rate = killed / total_mutations
        """
        import ast
        import subprocess
        import sys as _sys

        target_dir = task.params.get("target_dir", "src/governance/")
        # 默认 60 秒:pytest 启动 + 测试执行需要时间,Windows 上更慢
        test_timeout = task.params.get("test_timeout", 60)

        mutations = []
        killed = 0
        survived = 0

        for root, dirs, files in os.walk(target_dir):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        source = f.read()

                    tree = ast.parse(source)
                    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.BinOp, ast.Compare, ast.UnaryOp))]

                    for node in nodes:
                        original_code = ast.get_source_segment(source, node)
                        if not original_code:
                            continue

                        # 深拷贝 tree 并对副本应用变异(避免污染原 tree)
                        import copy
                        mutated_tree = copy.deepcopy(tree)
                        # 在 mutated_tree 中找到对应位置的 node(用位置匹配)
                        mutated_node = self._find_corresponding_node(mutated_tree, node)

                        mutation_type = self._apply_mutation(mutated_node) if mutated_node else ""

                        if not mutation_type:
                            continue

                        try:
                            mutated_code = ast.unparse(ast.fix_missing_locations(mutated_tree))
                            mutated_segment = (
                                ast.get_source_segment(mutated_code, mutated_node).strip()
                                if mutated_node else "N/A"
                            )

                            # P1-4 修复:真实测试执行替代 random.random()
                            is_killed = self._run_mutation_test(
                                filepath, mutated_code, test_timeout, _sys
                            )

                            mutations.append({
                                "file": filepath,
                                "type": mutation_type,
                                "original": original_code.strip(),
                                "mutated": mutated_segment,
                                "killed": is_killed
                            })

                            if is_killed:
                                killed += 1
                            else:
                                survived += 1
                        except Exception as e:
                            # P1-4: 严禁裸 except 吞异常,记录具体错误用于诊断
                            logger.warning(
                                f"Mutation test failed for {filepath} at "
                                f"line {getattr(node, 'lineno', '?')}: "
                                f"{type(e).__name__}: {e}",
                                exc_info=True,
                            )
                except Exception:
                    continue

        total_mutations = killed + survived
        kill_rate = round(killed / total_mutations, 2) if total_mutations > 0 else 0.0

        report = {
            "target_dir": target_dir,
            "kill_rate": kill_rate,
            "mutations": total_mutations,
            "killed": killed,
            "survived": survived,
            "status": "completed",
            "details": mutations[:10]
        }
        return {"status": "completed", "report": report}

    def _find_corresponding_node(self, tree, target_node):
        """在 tree 中根据位置信息查找与 target_node 对应的节点。"""
        import ast
        for n in ast.walk(tree):
            if (
                hasattr(n, "lineno") and hasattr(n, "col_offset")
                and n.lineno == target_node.lineno
                and n.col_offset == target_node.col_offset
                and type(n) == type(target_node)
            ):
                return n
        return None

    def _apply_mutation(self, node) -> str:
        """对 node 应用变异,返回变异类型描述(空字符串表示未变异)。

        注意:ast.Add/Sub/Gt 等操作符是单例,不接受 lineno/col_offset 参数。
        位置信息由父节点(BinOp/Compare)维护,无需在操作符上设置。
        """
        import ast

        if isinstance(node, ast.BinOp):
            mutation_map = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
            if type(node.op) in mutation_map:
                # 操作符单例不接受 lineno 参数,直接实例化
                node.op = mutation_map[type(node.op)]()
                return f"BinOp: {type(node.op).__name__}"

        elif isinstance(node, ast.Compare):
            if node.ops:
                comp_map = {ast.Gt: ast.Lt, ast.Lt: ast.Gt, ast.GtE: ast.LtE, ast.LtE: ast.GtE, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
                if type(node.ops[0]) in comp_map:
                    node.ops[0] = comp_map[type(node.ops[0])]()
                    return f"Compare: {type(node.ops[0]).__name__}"

        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                node.op = ast.UAdd()
                return "UnaryOp: Not->UAdd"

        return ""

    def _find_test_file(self, filepath: str) -> Optional[str]:
        """根据源文件路径查找对应测试文件。

        约定:src/X/Y.py → tests/X/test_Y.py
              src/Y.py → tests/test_Y.py
        """
        path = Path(filepath)
        parts = list(path.parts)

        if "src" not in parts:
            return None

        src_idx = parts.index("src")
        # 替换 src → tests
        test_parts = parts[:src_idx] + ["tests"] + parts[src_idx + 1:]
        # 文件名 Y.py → test_Y.py
        filename = test_parts[-1]
        if not filename.startswith("test_"):
            test_parts[-1] = "test_" + filename

        test_path = Path(*test_parts)
        if test_path.exists():
            return str(test_path)

        return None

    def _run_mutation_test(self, filepath: str, mutated_code: str, timeout: int, sys_module) -> bool:
        """运行变异测试:备份原文件,写入变异代码,运行 pytest,恢复原文件。

        Args:
            filepath: 源文件路径
            mutated_code: 变异后的完整源码
            timeout: pytest 超时秒数
            sys_module: sys 模块(用于获取 python 解释器路径)

        Returns:
            True 如果变异被测试发现(killed),False 如果变异存活
        """
        import subprocess

        # 查找对应测试文件
        test_file = self._find_test_file(filepath)
        if not test_file:
            # 无测试文件,无法检测变异,标记为存活
            return False

        # 备份原文件内容
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            logger.debug(f"Failed to read original file {filepath}: {e}")
            return False

        try:
            # 写入变异代码
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(mutated_code)

            # 运行 pytest(隔离子进程,避免污染当前进程状态)
            result = subprocess.run(
                [sys_module.executable, "-m", "pytest", test_file, "-x", "--tb=no", "-q"],
                capture_output=True,
                timeout=timeout,
                cwd=os.getcwd(),
            )

            # 测试失败(exit code != 0)→ 变异被检测到 → killed
            # 测试通过(exit code == 0)→ 变异存活 → survived
            return result.returncode != 0

        except subprocess.TimeoutExpired:
            # 超时视为变异存活(测试卡住,无法判定)
            logger.debug(f"Mutation test timed out for {filepath}")
            return False
        except Exception as e:
            logger.debug(f"Mutation test execution failed for {filepath}: {e}")
            return False
        finally:
            # 恢复原文件(确保不破坏源码)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(original_content)
            except Exception as e:
                logger.error(f"Failed to restore original file {filepath}: {e}")

    async def _handle_approval_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.governance.approval import ApprovalManager

        manager = ApprovalManager()
        tx_id = task.params.get("tx_id")
        action = task.params.get("action", "approve")
        approver = task.params.get("approver", "system")

        if tx_id is None:
            return {"status": "failed", "error": "tx_id is required"}

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
            health_monitor.record_diagnosis(success=True)
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

    async def _handle_ai_evaluate_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.ai.evaluator import AIEvaluator

        evaluator = AIEvaluator()
        output = task.params.get("output", "")
        expected = task.params.get("expected", "")

        if not output:
            return {"status": "failed", "error": "output is required"}
        if not expected:
            return {"status": "failed", "error": "expected is required"}

        result = evaluator.evaluate(output, expected)
        return {"status": "completed", "evaluation": result.to_dict()}

    async def _handle_ai_classify_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.ai.classifier import AITextClassifier

        classifier = AITextClassifier()
        text = task.params.get("text", "")

        if not text:
            return {"status": "failed", "error": "text is required"}

        result = classifier.classify(text)
        return {"status": "completed", "classification": result.to_dict()}

    async def _handle_ai_qa_task(self, task: WorkflowTask, params: Dict[str, Any], prev_results: Dict[str, Any]) -> Dict[str, Any]:
        from src.ai.qa_engine import AIQAEngine

        qa_engine = AIQAEngine()
        question = task.params.get("question", "")
        context = task.params.get("context", None)

        if not question:
            return {"status": "failed", "error": "question is required"}

        answer = qa_engine.answer(question, context)
        return {"status": "completed", "qa": answer.to_dict()}

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
        with self._lock:
            return [
                {"id": wid, "name": w.name, "description": w.description, "task_count": len(w.tasks)}
                for wid, w in self.workflows.items()
            ]

    def list_instances(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            instances: list[WorkflowInstance] = list(self.instances.values())
            if workflow_id:
                instances = [i for i in instances if i.workflow_id == workflow_id]

            return [
                {
                    "instance_id": i.instance_id,
                    "workflow_id": i.workflow_id,
                    "status": i.status.value,
                    "created_at": i.created_at.isoformat(),
                    "task_count": len(i.tasks),
                }
                for i in instances
            ]

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            if workflow_id not in self.workflows:
                return False
            
            del self.workflows[workflow_id]
            
            self.instances = {
                inst_id: inst for inst_id, inst in self.instances.items()
                if inst.workflow_id != workflow_id
            }
            
            if self._use_database and self._db:
                try:
                    self._db.delete_many(
                        self._db.workflows_table,
                        self._db.workflows_table.c.workflow_id == workflow_id,
                    )
                    self._db.delete_many(
                        self._db.workflow_instances_table,
                        self._db.workflow_instances_table.c.workflow_id == workflow_id,
                    )
                except Exception as e:
                    logger.warning(f"Database delete failed: {e}")
            
            logger.info(f"Deleted workflow: {workflow_id}")
            return True