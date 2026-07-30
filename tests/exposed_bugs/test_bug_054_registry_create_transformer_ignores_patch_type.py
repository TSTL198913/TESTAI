import pytest
from src.governance.registry import GovernanceRegistry, PatchType


class TestRegistryCreateTransformerIgnoresPatchType:
    def test_registry_is_initialized(self):
        print(f"Registry contents: {GovernanceRegistry._registry}")
        print(f"SECURITY in registry: {PatchType.SECURITY in GovernanceRegistry._registry}")
        assert PatchType.SECURITY in GovernanceRegistry._registry
        assert PatchType.PERFORMANCE in GovernanceRegistry._registry

    def test_create_transformer_uses_patch_type(self):
        result1 = GovernanceRegistry.create_transformer(
            patch_type=PatchType.SECURITY,
            target_function="test_func",
            new_body="pass",
        )
        
        result2 = GovernanceRegistry.create_transformer(
            patch_type=PatchType.PERFORMANCE,
            target_function="test_func",
            new_body="pass",
        )
        
        assert type(result1).__name__ == "ContextAwareTransformer", \
            f"Expected ContextAwareTransformer for SECURITY, got {type(result1).__name__}"
        assert type(result2).__name__ == "FunctionTransformer", \
            f"Expected FunctionTransformer for PERFORMANCE, got {type(result2).__name__}"