import pytest
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType, WorkflowStatus


class TestAIWorkflowIntegration:
    @pytest.fixture(autouse=True)
    def reset_engine(self):
        engine = WorkflowEngine()
        with engine._lock:
            engine.instances.clear()
        yield

    @pytest.mark.asyncio
    async def test_ai_evaluate_task_handler(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI评估测试",
            description="测试AI评估任务",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_EVALUATE,
                    name="测试评估",
                    params={
                        "output": "Hello World",
                        "expected": "Hello World",
                    },
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        assert len(task_results) == 1
        
        first_task_id = list(task_results.keys())[0]
        task_result = task_results[first_task_id]
        assert task_result["status"] == "completed"
        assert "result" in task_result
        
        inner_result = task_result["result"]
        assert inner_result["status"] == "completed"
        assert "evaluation" in inner_result
        
        evaluation = inner_result["evaluation"]
        assert evaluation["grade"] == "excellent"
        assert evaluation["score"] >= 0.9
        assert evaluation["matches_expected"] is True

    @pytest.mark.asyncio
    async def test_ai_evaluate_task_with_mismatch(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI评估不匹配测试",
            description="测试AI评估任务不匹配场景",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_EVALUATE,
                    name="测试评估",
                    params={
                        "output": "Hello World",
                        "expected": "Goodbye World",
                    },
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert "evaluation" in inner_result
        evaluation = inner_result["evaluation"]
        assert evaluation["matches_expected"] is False

    @pytest.mark.asyncio
    async def test_ai_evaluate_task_missing_params(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI评估缺失参数测试",
            description="测试AI评估任务缺失参数",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_EVALUATE,
                    name="测试评估",
                    params={"output": "Hello World"},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert inner_result["status"] == "failed"
        assert "error" in inner_result

    @pytest.mark.asyncio
    async def test_ai_classify_task_handler(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI分类测试",
            description="测试AI分类任务",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_CLASSIFY,
                    name="测试分类",
                    params={"text": "AssertionError: expected 5 but got 3"},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert inner_result["status"] == "completed"
        assert "classification" in inner_result
        
        classification = inner_result["classification"]
        assert classification["category"] == "logic_error"

    @pytest.mark.asyncio
    async def test_ai_classify_task_missing_text(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI分类缺失参数测试",
            description="测试AI分类任务缺失参数",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_CLASSIFY,
                    name="测试分类",
                    params={},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert inner_result["status"] == "failed"
        assert "error" in inner_result

    @pytest.mark.asyncio
    async def test_ai_qa_task_handler(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI问答测试",
            description="测试AI问答任务",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_QA,
                    name="测试问答",
                    params={"question": "什么是变异测试？"},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert inner_result["status"] == "completed"
        assert "qa" in inner_result
        
        qa_result = inner_result["qa"]
        assert "answer" in qa_result
        assert len(qa_result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_ai_qa_task_missing_question(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="AI问答缺失参数测试",
            description="测试AI问答任务缺失参数",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_QA,
                    name="测试问答",
                    params={},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        
        task_results = status["tasks"]
        first_task_id = list(task_results.keys())[0]
        inner_result = task_results[first_task_id]["result"]
        
        assert inner_result["status"] == "failed"
        assert "error" in inner_result

    @pytest.mark.asyncio
    async def test_combined_ai_workflow(self):
        engine = WorkflowEngine()
        
        workflow = WorkflowDefinition(
            name="组合AI工作流测试",
            description="测试包含多种AI任务的工作流",
            tasks=[
                WorkflowTask(
                    type=TaskType.AI_EVALUATE,
                    name="评估任务",
                    params={
                        "output": "Success",
                        "expected": "Success",
                    },
                ),
                WorkflowTask(
                    type=TaskType.AI_CLASSIFY,
                    name="分类任务",
                    params={"text": "TimeoutError: operation timed out"},
                ),
                WorkflowTask(
                    type=TaskType.AI_QA,
                    name="问答任务",
                    params={"question": "如何提高测试覆盖率？"},
                ),
            ],
        )
        
        workflow_id = engine.define_workflow(workflow)
        result = await engine.execute_workflow(workflow_id)
        instance_id = result["instance_id"]
        
        status = engine.get_workflow_status(instance_id)
        assert status is not None
        assert status["status"] == WorkflowStatus.COMPLETED.value
        
        task_results = status["tasks"]
        assert len(task_results) == 3
        
        has_evaluation = False
        has_classification = False
        has_qa = False
        
        for tid in task_results:
            inner_result = task_results[tid]["result"]
            if "evaluation" in inner_result:
                has_evaluation = True
            if "classification" in inner_result:
                has_classification = True
            if "qa" in inner_result:
                has_qa = True
        
        assert has_evaluation and has_classification and has_qa