import pytest
from src.governance.orchestrator import GovernanceOrchestrator


class TestOrchestratorPathTraversal:
    def test_resolve_file_path_rejects_path_traversal(self):
        orchestrator = GovernanceOrchestrator()
        
        malicious_component = "../../etc/passwd"
        with pytest.raises(ValueError):
            orchestrator._resolve_file_path(malicious_component)
    
    def test_resolve_file_path_rejects_slash_in_component(self):
        orchestrator = GovernanceOrchestrator()
        
        malicious_component = "component/../../../etc/passwd"
        with pytest.raises(ValueError):
            orchestrator._resolve_file_path(malicious_component)
    
    def test_resolve_file_path_accepts_valid_component(self):
        orchestrator = GovernanceOrchestrator()
        
        valid_component = "TestComponent"
        resolved_path = orchestrator._resolve_file_path(valid_component)
        
        assert "TestComponent" in resolved_path
        assert resolved_path.endswith(".py")