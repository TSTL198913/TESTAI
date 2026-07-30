import threading
import pytest
import asyncio
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType, WorkflowStatus


class TestWorkflowEngineThreadSafety:
    def setup_method(self):
        pass

    def test_concurrent_workflow_definition(self):
        engine = WorkflowEngine()
        errors = []
        workflow_ids = []
        lock = threading.Lock()

        def define_workflow(index):
            try:
                definition = WorkflowDefinition(
                    name=f"Concurrent Workflow {index}",
                    description=f"Created by thread {index}",
                    tasks=[
                        WorkflowTask(
                            type=TaskType.GOVERNANCE,
                            name="Test Task",
                        )
                    ],
                )
                wf_id = engine.define_workflow(definition)
                with lock:
                    workflow_ids.append(wf_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=define_workflow, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(workflow_ids) == 10, f"Expected 10 workflows, got {len(workflow_ids)}"

    def test_get_workflow_status_without_lock(self):
        engine = WorkflowEngine()
        
        test_instance = None
        for inst_id, inst in engine.instances.items():
            test_instance = inst_id
            break
        
        if test_instance:
            result = engine.get_workflow_status(test_instance)
            assert result is not None
            assert "instance_id" in result
            assert "status" in result

    def test_concurrent_list_workflows(self):
        engine = WorkflowEngine()
        errors = []

        def list_workflows():
            try:
                workflows = engine.list_workflows()
                assert isinstance(workflows, list)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t = threading.Thread(target=list_workflows)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors during list: {errors}"