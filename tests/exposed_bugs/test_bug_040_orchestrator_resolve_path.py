import pytest
from src.governance.orchestrator import GovernanceOrchestrator


class TestOrchestratorResolvePath:
    def test_resolve_file_path_returns_valid_path(self):
        orchestrator = GovernanceOrchestrator()
        
        path = orchestrator._resolve_file_path("EvalPlatformProcessor")
        assert path == "extensions/eval_platform/processor.py"

    def test_resolve_file_path_uses_default_for_unknown_component(self):
        orchestrator = GovernanceOrchestrator()
        
        path = orchestrator._resolve_file_path("UnknownComponent")
        assert path == "src/engine/processor/unknowncomponent.py"

    def test_resolve_file_path_handles_empty_component(self):
        orchestrator = GovernanceOrchestrator()
        
        path = orchestrator._resolve_file_path("")
        assert path.endswith(".py"), "空字符串应返回 .py 后缀的路径"

    def test_resolve_file_path_handles_none_component(self):
        orchestrator = GovernanceOrchestrator()
        
        path = orchestrator._resolve_file_path(None)
        assert path == "src/engine/processor/none.py", \
            "None should be handled gracefully instead of raising AttributeError"