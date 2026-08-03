import os

import pytest
import libcst as cst

from src.governance.transformer import FunctionTransformer, ContextAwareTransformer, ImportApplier
from src.governance.process_manager import ProcessManager
from src.governance.security import SecurePathValidator


class TestTransformerValidation:
    def test_tn_01_patches_correct_method_in_class(self):
        transformer = ContextAwareTransformer(
            target_function="test_func",
            new_body="return 1",
            target_class="TestClass",
        )
        
        code = """
class TestClass:
    def test_func(self):
        return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(transformer)
        assert transformer.patched is True
        assert "return 1" in cst.Module(result.body).code

    def test_tn_02_rejects_wrong_class_name(self):
        transformer = ContextAwareTransformer(
            target_function="test_func",
            new_body="return 1",
            target_class="WrongClass",
        )
        
        code = """
class TestClass:
    def test_func(self):
        return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(transformer)
        assert transformer.patched is False

    def test_tn_03_handles_empty_new_body(self):
        transformer = ContextAwareTransformer(
            target_function="test_func",
            new_body="",
            target_class="TestClass",
        )
        
        code = """
class TestClass:
    def test_func(self):
        return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(transformer)
        assert transformer.patched is True

    def test_tn_06_patches_standalone_function(self):
        transformer = FunctionTransformer(
            target_function="test_func",
            new_body="return 1",
        )
        
        code = """
def test_func():
    return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(transformer)
        assert transformer.patched is True
        assert "return 1" in cst.Module(result.body).code

    def test_tn_07_ignores_non_matching_function(self):
        transformer = FunctionTransformer(
            target_function="wrong_func",
            new_body="return 1",
        )
        
        code = """
def test_func():
    return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(transformer)
        assert transformer.patched is False

    def test_tn_08_adds_imports_at_correct_position(self):
        applier = ImportApplier(["import os"])
        
        code = """
def test_func():
    return 0
"""
        
        module = cst.parse_module(code)
        result = module.visit(applier)
        output = cst.Module(result.body).code
        assert "import os" in output
        assert output.index("import os") < output.index("def test_func")


class TestProcessManagerValidation:
    def test_process_manager_singleton(self):
        pm1 = ProcessManager()
        pm2 = ProcessManager()
        assert pm1 is pm2

    def test_register_and_monitor_process(self):
        pm = ProcessManager()
        pm.register_process(12345, "test_command", timeout=30)
        info = pm.get_process(12345)
        assert info is not None
        assert info.pid == 12345
        assert info.command == "test_command"

    def test_is_process_alive(self):
        pm = ProcessManager()
        assert pm._is_process_alive(999999) is False

    def test_kill_nonexistent_process(self):
        pm = ProcessManager()
        result = pm.kill_process(999999)
        assert isinstance(result, bool)


class TestSecurityValidation:
    def test_validate_path_returns_false_for_invalid_path(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path("../../etc/passwd")
        assert valid is False
        valid, msg = validator.validate_path("test\x00file.py")
        assert valid is False
        valid, msg = validator.validate_path("a" * 300)
        assert valid is False

    def test_validate_path_returns_true_for_valid_path(self):
        # 使用项目根下 src/ 子目录的合法绝对路径
        project_root = os.path.abspath(".")
        validator = SecurePathValidator(project_root=project_root)
        valid_path = os.path.join(project_root, "src", "governance", "transformer.py")
        valid, msg = validator.validate_path(valid_path)
        assert valid is True, f"合法路径应通过校验: {valid_path}, msg={msg}"

    def test_is_sandboxed(self):
        project_root = os.path.abspath(".")
        validator = SecurePathValidator(project_root=project_root)
        valid_path = os.path.join(project_root, "src", "governance", "transformer.py")
        assert validator.is_sandboxed(valid_path) is True
        assert validator.is_sandboxed("../../etc/passwd") is False

    def test_sanitize_path(self):
        validator = SecurePathValidator()
        result = validator.sanitize_path("transformer.py", "/src/governance")
        assert result.endswith("transformer.py")
        with pytest.raises(ValueError):
            validator.sanitize_path("../../etc/passwd", "/src/governance")


class TestCIGuardEffectiveness:
    def test_ci_guard_blocks_weak_assertion(self):
        test_file = os.path.join("tests", "governance", "test_temp_weak.py")

        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("""
import pytest

def test_weak():
    obj = {"attr": 1}
    assert hasattr(obj, 'attr')
""")

            from tests.ci_guard import scan_for_weak_assertions

            violations = scan_for_weak_assertions(os.path.dirname(test_file))

            assert len(violations) > 0, "CI 守卫未能检测到弱断言"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_ci_guard_blocks_pytest_skip(self):
        test_file = os.path.join("tests", "governance", "test_temp_skip.py")

        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("""
import pytest

def test_skipped():
    pytest.skip("broken")
""")

            from tests.ci_guard import scan_for_pytest_skip

            violations = scan_for_pytest_skip(os.path.dirname(test_file))

            assert len(violations) > 0, "CI 守卫未能检测到 pytest.skip"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_ci_guard_blocks_exception_pass(self):
        test_file = os.path.join("tests", "governance", "test_temp_pass.py")

        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("""
def test_pass():
    try:
        raise ValueError("test")
    except Exception:
        pass
""")

            from tests.ci_guard import scan_for_exception_pass

            violations = scan_for_exception_pass(os.path.dirname(test_file))

            assert len(violations) > 0, "CI 守卫未能检测到 except Exception: pass"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)