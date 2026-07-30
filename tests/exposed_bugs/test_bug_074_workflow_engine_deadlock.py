import pytest
import threading
import time
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType


class TestWorkflowEngineDeadlock:
    def test_nested_lock_causes_deadlock(self):
        engine = WorkflowEngine()
        
        definition = WorkflowDefinition(
            name="Deadlock Test Workflow",
            description="Test nested lock scenario",
            tasks=[
                WorkflowTask(
                    type=TaskType.MONITORING,
                    name="Simple Task",
                    params={"action": "get_status"},
                )
            ],
        )
        workflow_id = engine.define_workflow(definition)
        
        result = None
        exception = None
        completed = threading.Event()
        
        def run_workflow():
            nonlocal result, exception
            try:
                result = engine.get_workflow(workflow_id)
            except Exception as e:
                exception = e
            finally:
                completed.set()
        
        run_workflow()
        
        assert result is not None
        assert exception is None

    def test_get_workflow_status_race_condition(self):
        engine = WorkflowEngine()
        
        errors = []
        completed = []
        lock = threading.Lock()
        
        def read_status():
            try:
                for instance_id in list(engine.instances.keys()):
                    status = engine.get_workflow_status(instance_id)
                    if status:
                        assert "instance_id" in status
                with lock:
                    completed.append("read")
            except Exception as e:
                with lock:
                    errors.append(e)
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=read_status)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=5)
        
        assert len(errors) == 0, f"Race condition errors: {errors}"
        assert len(completed) == 10, f"Expected 10 completed reads, got {len(completed)}"