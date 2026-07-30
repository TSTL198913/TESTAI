import pytest
import os
from unittest.mock import patch, MagicMock
from src.platform.workflow import WorkflowEngine


class TestWorkflowEngineMutationTestCleanup:
    def test_mutation_test_always_restores_original_file(self, tmp_path):
        test_file = tmp_path / "test_module.py"
        original_content = """def add(a, b):
    return a + b
"""
        test_file.write_text(original_content, encoding="utf-8")

        engine = WorkflowEngine()

        mutated_code = """def add(a, b):
    return a - b
"""

        with patch.object(engine, '_find_test_file', return_value=str(tmp_path / "test_test_module.py")):
            with patch('subprocess.run', side_effect=Exception("Simulated error")):
                try:
                    engine._run_mutation_test(str(test_file), mutated_code, 10, MagicMock())
                except Exception:
                    pass

        assert test_file.read_text(encoding="utf-8") == original_content, \
            "Original file content should be restored after mutation test"

    def test_mutation_test_no_temp_files_left(self, tmp_path):
        test_file = tmp_path / "test_module.py"
        test_file.write_text("def func(): pass", encoding="utf-8")

        engine = WorkflowEngine()

        with patch.object(engine, '_find_test_file', return_value=str(tmp_path / "test_test_module.py")):
            with patch('subprocess.run', return_value=MagicMock(returncode=1)):
                engine._run_mutation_test(str(test_file), "mutated code", 10, MagicMock())

        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "No temporary files should remain after mutation test"