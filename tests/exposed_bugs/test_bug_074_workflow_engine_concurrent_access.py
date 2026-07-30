import pytest
import threading
import asyncio
import time
from src.platform.workflow import WorkflowEngine, WorkflowDefinition, WorkflowTask, TaskType, WorkflowStatus


class TestWorkflowEngineConcurrentAccess:
    def test_get_workflow_status_no_lock_protection(self):
        engine = WorkflowEngine()
        
        definition = WorkflowDefinition(
            name="Concurrent Access Test",
            description="Test race condition",
            tasks=[
                WorkflowTask(
                    type=TaskType.DELAY,
                    name="Delay Task",
                    params={"seconds": 0.1},
                )
            ],
        )
        workflow_id = engine.define_workflow(definition)
        
        errors = []
        lock = threading.Lock()
        
        def read_status_loop():
            for _ in range(50):
                try:
                    for instance_id in engine.instances.keys():
                        status = engine.get_workflow_status(instance_id)
                        if status:
                            assert isinstance(status, dict)
                except Exception as e:
                    with lock:
                        errors.append(e)
                time.sleep(0.001)
        
        def execute_workflows():
            for _ in range(5):
                asyncio.run(engine.execute_workflow(workflow_id))
                time.sleep(0.05)
        
        read_thread = threading.Thread(target=read_status_loop)
        write_thread = threading.Thread(target=execute_workflows)
        
        read_thread.start()
        write_thread.start()
        
        read_thread.join(timeout=30)
        write_thread.join(timeout=30)
        
        assert len(errors) == 0, f"Race condition detected: {errors}"

    def test_list_workflows_during_execution(self):
        engine = WorkflowEngine()
        
        definition = WorkflowDefinition(
            name="List During Execution",
            description="Test concurrent list",
            tasks=[
                WorkflowTask(
                    type=TaskType.DELAY,
                    name="Delay Task",
                    params={"seconds": 0.2},
                )
            ],
        )
        workflow_id = engine.define_workflow(definition)
        
        errors = []
        lock = threading.Lock()
        
        def list_loop():
            for _ in range(20):
                try:
                    workflows = engine.list_workflows()
                    assert isinstance(workflows, list)
                except Exception as e:
                    with lock:
                        errors.append(e)
                time.sleep(0.02)
        
        list_thread = threading.Thread(target=list_loop)
        list_thread.start()
        
        asyncio.run(engine.execute_workflow(workflow_id))
        
        list_thread.join(timeout=30)
        
        assert len(errors) == 0, f"Race condition during list: {errors}"