"""
WorkflowEngine 单元测试
覆盖:
1. WorkflowDefinition 验证逻辑 (name/task_count/description)
2. _calculate_execution_order 拓扑排序 + 循环依赖检测
3. _apply_mutation AST 变异逻辑
4. _find_test_file 路径解析逻辑
5. WorkflowTask 序列化/反序列化
"""

import pytest
import ast

from src.platform.workflow import (
    WorkflowDefinition,
    WorkflowTask,
    TaskType,
    WorkflowEngine,
)


# ==================== WorkflowDefinition 验证 ====================

class TestWorkflowDefinitionValidation:
    """WorkflowDefinition 的 Pydantic 验证逻辑测试"""

    def test_valid_workflow_definition(self):
        """合法定义应通过验证"""
        wf = WorkflowDefinition(
            name="Test Workflow",
            description="A valid workflow",
            tasks=[
                WorkflowTask(type=TaskType.GOVERNANCE, name="Task 1"),
                WorkflowTask(type=TaskType.MONITORING, name="Task 2"),
            ],
        )
        assert wf.name == "Test Workflow"
        assert len(wf.tasks) == 2

    def test_empty_name_raises_error(self):
        """空名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称不能为空"):
            WorkflowDefinition(name="", tasks=[])

    def test_whitespace_name_raises_error(self):
        """纯空格名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称不能为空"):
            WorkflowDefinition(name="   ", tasks=[])

    def test_long_name_raises_error(self):
        """超过 100 字符的名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称不能超过100个字符"):
            WorkflowDefinition(name="A" * 101, tasks=[])

    def test_xss_in_name_raises_error(self):
        """包含 XSS 脚本的名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称包含非法字符"):
            WorkflowDefinition(name="<script>alert('xss')</script>", tasks=[])

    def test_sql_injection_in_name_raises_error(self):
        """包含 SQL 注入的名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称包含非法字符"):
            WorkflowDefinition(name="' OR '1'='1", tasks=[])

    def test_path_traversal_in_name_raises_error(self):
        """包含路径穿越的名称应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流名称包含非法字符"):
            WorkflowDefinition(name="../../etc/passwd", tasks=[])

    def test_invalid_task_count(self):
        """无效的 task_count 应抛出 ValueError"""
        with pytest.raises(ValueError):
            WorkflowDefinition(name="Test", tasks=[], task_count=-1)

        with pytest.raises(ValueError):
            WorkflowDefinition(name="Test", tasks=[], task_count=1001)

        with pytest.raises(ValueError):
            WorkflowDefinition(name="Test", tasks=[], task_count="abc")

    def test_long_description_raises_error(self):
        """超过 1000 字符的描述应抛出 ValueError"""
        with pytest.raises(ValueError, match="工作流描述不能超过1000个字符"):
            WorkflowDefinition(name="Test", description="D" * 1001, tasks=[])

    def test_to_dict_and_from_dict_roundtrip(self):
        """to_dict / from_dict 序列化往返测试"""
        wf = WorkflowDefinition(
            name="Roundtrip",
            description="Test roundtrip",
            tasks=[
                WorkflowTask(type=TaskType.GOVERNANCE, name="G1", params={"k": "v"}),
            ],
        )
        wf_dict = wf.to_dict()
        wf_restored = WorkflowDefinition.from_dict(wf_dict)

        assert wf_restored.name == wf.name
        assert wf_restored.description == wf.description
        assert len(wf_restored.tasks) == 1
        assert wf_restored.tasks[0].type == TaskType.GOVERNANCE
        assert wf_restored.tasks[0].name == "G1"
        assert wf_restored.tasks[0].params == {"k": "v"}


# ==================== WorkflowTask 序列化 ====================

class TestWorkflowTaskSerialization:
    def test_to_dict(self):
        task = WorkflowTask(
            type=TaskType.APPROVAL,
            name="Approve Patch",
            params={"tx_id": "tx-123"},
            depends_on=["task-1"],
            timeout=30,
        )
        d = task.to_dict()
        assert d["type"] == "approval"
        assert d["name"] == "Approve Patch"
        assert d["params"] == {"tx_id": "tx-123"}
        assert d["depends_on"] == ["task-1"]
        assert d["timeout"] == 30
        assert "id" in d  # UUID auto-generated

    def test_from_dict_with_id(self):
        data = {
            "type": "mutation_test",
            "name": "Mutation Test",
            "id": "custom-id",
            "params": {"target_dir": "src/"},
        }
        task = WorkflowTask.from_dict(data)
        assert task.id == "custom-id"
        assert task.type == TaskType.MUTATION_TEST
        assert task.params == {"target_dir": "src/"}

    def test_from_dict_without_id(self):
        data = {"type": "delay", "name": "Wait"}
        task = WorkflowTask.from_dict(data)
        assert task.id is not None  # UUID auto-generated
        assert task.timeout == 60  # default


# ==================== WorkflowEngine._calculate_execution_order ====================

class TestTopologicalSort:
    def _make_engine(self):
        """创建一个不触发数据库连接的引擎实例"""
        # 由于 WorkflowEngine 是单例, 我们需要直接测试方法
        # 这里我们通过 mock 绕过数据库初始化
        import os
        old_env = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = ""  # 禁用数据库
        try:
            # WorkflowEngine 是单例, 如果已初始化则直接返回
            # 但在测试中我们需要一个干净的实例
            # 所以我们直接创建一个实例或测试静态方法
            engine = WorkflowEngine()
            # 重置实例以便测试 (仅用于测试)
            WorkflowEngine._instance = None
            engine2 = WorkflowEngine()
            return engine2
        finally:
            if old_env is not None:
                os.environ["DATABASE_URL"] = old_env

    def test_simple_linear_dependency(self):
        """简单线性依赖: A -> B -> C"""
        engine = self._make_engine()
        # 先创建任务, 获得它们的 ID
        task_c = WorkflowTask(type=TaskType.APPROVAL, name="C")
        task_b = WorkflowTask(type=TaskType.MONITORING, name="B", depends_on=[task_c.id])
        task_a = WorkflowTask(type=TaskType.GOVERNANCE, name="A", depends_on=[task_b.id])
        tasks = [task_a, task_b, task_c]
        
        order = engine._calculate_execution_order(tasks)
        # C 无依赖, 应先执行
        assert order[0] == task_c.id
        # B 依赖 C, 应其次
        assert order[1] == task_b.id
        # A 依赖 B, 应最后
        assert order[2] == task_a.id

    def test_no_dependencies(self):
        """无依赖: 执行顺序不变"""
        engine = self._make_engine()
        tasks = [
            WorkflowTask(type=TaskType.GOVERNANCE, name="A"),
            WorkflowTask(type=TaskType.MONITORING, name="B"),
            WorkflowTask(type=TaskType.APPROVAL, name="C"),
        ]
        order = engine._calculate_execution_order(tasks)
        assert len(order) == 3

    def test_parallel_tasks(self):
        """并行任务: A 和 B 都依赖 C, C 应先执行"""
        engine = self._make_engine()
        task_c = WorkflowTask(type=TaskType.APPROVAL, name="C")
        task_a = WorkflowTask(type=TaskType.GOVERNANCE, name="A", depends_on=[task_c.id])
        task_b = WorkflowTask(type=TaskType.MONITORING, name="B", depends_on=[task_c.id])
        tasks = [task_a, task_b, task_c]
        
        order = engine._calculate_execution_order(tasks)
        # C 必须第一个
        assert order[0] == task_c.id
        # A 和 B 可以是任意顺序
        assert set(order[1:]) == {task_a.id, task_b.id}

    def test_circular_dependency_raises_error(self):
        """循环依赖应抛出 ValueError"""
        engine = self._make_engine()
        # 先创建 A, 再创建 B, 然后设置循环依赖
        task_a = WorkflowTask(type=TaskType.GOVERNANCE, name="A")
        task_b = WorkflowTask(type=TaskType.MONITORING, name="B", depends_on=[task_a.id])
        # 强制修改 A 的 depends_on 以包含 B, 形成循环
        task_a.depends_on = [task_b.id]
        
        tasks = [task_a, task_b]
        with pytest.raises(ValueError, match="Circular dependency detected"):
            engine._calculate_execution_order(tasks)


# ==================== WorkflowEngine._apply_mutation ====================

class TestApplyMutation:
    def _make_engine(self):
        import os
        old_env = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = ""
        try:
            WorkflowEngine._instance = None
            return WorkflowEngine()
        finally:
            if old_env is not None:
                os.environ["DATABASE_URL"] = old_env

    def test_add_to_subtraction_mutation(self):
        """Add -> Sub 变异"""
        engine = self._make_engine()
        code = "x + y"
        tree = ast.parse(code)
        # 找到 BinOp 节点
        binop_node = tree.body[0].value
        assert isinstance(binop_node, ast.BinOp)
        assert isinstance(binop_node.op, ast.Add)

        mutation_type = engine._apply_mutation(binop_node)
        assert mutation_type == "BinOp: Sub"
        assert isinstance(binop_node.op, ast.Sub)

    def test_subtraction_to_add_mutation(self):
        """Sub -> Add 变异"""
        engine = self._make_engine()
        code = "x - y"
        tree = ast.parse(code)
        binop_node = tree.body[0].value
        engine._apply_mutation(binop_node)
        assert isinstance(binop_node.op, ast.Add)

    def test_gt_to_lt_mutation(self):
        """Gt -> Lt 变异"""
        engine = self._make_engine()
        code = "x > y"
        tree = ast.parse(code)
        compare_node = tree.body[0].value
        assert isinstance(compare_node, ast.Compare)

        mutation_type = engine._apply_mutation(compare_node)
        assert mutation_type == "Compare: Lt"
        assert isinstance(compare_node.ops[0], ast.Lt)

    def test_eq_to_noteq_mutation(self):
        """Eq -> NotEq 变异"""
        engine = self._make_engine()
        code = "x == y"
        tree = ast.parse(code)
        compare_node = tree.body[0].value
        engine._apply_mutation(compare_node)
        assert isinstance(compare_node.ops[0], ast.NotEq)

    def test_not_to_uadd_mutation(self):
        """UnaryOp(Not) -> UAdd 变异"""
        engine = self._make_engine()
        code = "not x"
        tree = ast.parse(code)
        unary_node = tree.body[0].value
        assert isinstance(unary_node, ast.UnaryOp)
        assert isinstance(unary_node.op, ast.Not)

        mutation_type = engine._apply_mutation(unary_node)
        assert mutation_type == "UnaryOp: Not->UAdd"
        assert isinstance(unary_node.op, ast.UAdd)

    def test_unsupported_mutation_returns_empty(self):
        """不支持的变异节点返回空字符串"""
        engine = self._make_engine()
        # Str 常量节点不是 BinOp/Compare/UnaryOp
        str_node = ast.Constant(value="hello")
        mutation_type = engine._apply_mutation(str_node)
        assert mutation_type == ""


# ==================== WorkflowEngine._find_test_file ====================

class TestFindTestFile:
    def _make_engine(self):
        import os
        old_env = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = ""
        try:
            WorkflowEngine._instance = None
            return WorkflowEngine()
        finally:
            if old_env is not None:
                os.environ["DATABASE_URL"] = old_env

    def test_src_module_to_tests(self):
        """src/X/Y.py -> tests/X/test_Y.py"""
        engine = self._make_engine()
        result = engine._find_test_file("src/platform/workflow.py")
        # 逻辑: src/platform/workflow.py -> tests/platform/test_workflow.py
        # tests/platform/test_workflow.py 存在 (见目录列表)
        assert result is not None
        # 使用 Path 进行跨平台比较
        from pathlib import Path
        assert Path(result) == Path("tests/platform/test_workflow.py")

    def test_no_src_prefix_returns_none(self):
        """无 src/ 前缀返回 None"""
        engine = self._make_engine()
        result = engine._find_test_file("other/module.py")
        assert result is None