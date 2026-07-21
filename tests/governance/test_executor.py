import pytest
import tempfile
import os
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock

import libcst as cst

from src.governance.executor import SecurityVisitor, GovernanceExecutor
from src.governance.registry import PatchType


class TestSecurityVisitor:
    """SecurityVisitor 安全访问器测试"""

    def test_forbidden_function_eval(self):
        code = 'eval("os.system(\'rm -rf /\')")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "eval" in visitor.unsafe_reason

    def test_forbidden_function_exec(self):
        code = 'exec("malicious_code")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "exec" in visitor.unsafe_reason

    def test_forbidden_function_compile(self):
        code = 'compile("bad_code", "<string>", "exec")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "compile" in visitor.unsafe_reason

    def test_forbidden_attribute_os(self):
        code = 'os.system("bad_command")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "os" in visitor.unsafe_reason

    def test_forbidden_attribute_subprocess(self):
        code = 'subprocess.run("bad_command")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is True
        assert "subprocess" in visitor.unsafe_reason

    def test_safe_code(self):
        code = 'def safe_function():\n    return "safe"'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is False
        assert visitor.unsafe_reason == ""

    def test_nested_attribute_access(self):
        code = 'some_obj.os.system("cmd")'
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        assert visitor.is_unsafe is False


class TestGovernanceExecutor:
    """GovernanceExecutor 治理执行器测试"""

    def setup_method(self):
        self.executor = GovernanceExecutor()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_file_path_valid(self):
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
            result = self.executor.validate_file_path("/valid/path.py")
            assert result is True

    def test_validate_file_path_invalid(self):
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(False, "Invalid path")):
            result = self.executor.validate_file_path("/invalid/path.py")
            assert result is False

    def test_is_safe_patch_safe(self):
        code = 'def safe():\n    return 1'
        result = self.executor.is_safe_patch(code)
        assert result is True

    def test_is_safe_patch_unsafe(self):
        code = 'eval("bad_code")'
        result = self.executor.is_safe_patch(code)
        assert result is False

    def test_is_safe_patch_parse_error(self):
        code = 'def invalid('
        result = self.executor.is_safe_patch(code)
        assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_unsafe_code(self):
        code = 'eval("bad")'
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
            result = await self.executor.apply_patch(
                file_path="/tmp/test.py",
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code=code,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_invalid_path(self):
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(False, "Invalid")):
            result = await self.executor.apply_patch(
                file_path="/invalid/path.py",
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return 1',
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_file_not_found(self):
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
            result = await self.executor.apply_patch(
                file_path="/nonexistent/file.py",
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return 1',
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_no_write_permission(self):
        test_file = Path(self.temp_dir) / "no_permission.py"
        test_file.write_text('def test():\n    return "original"')
        
        test_file.chmod(stat.S_IRUSR)
        
        with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
            result = await self.executor.apply_patch(
                file_path=str(test_file),
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return "patched"',
            )
        
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert result is True

    @pytest.mark.asyncio
    async def test_apply_patch_backup_failure(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch('shutil.copy2', side_effect=Exception("Backup failed")):
            with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
                result = await self.executor.apply_patch(
                    file_path=str(test_file),
                    patch_type=PatchType.SECURITY,
                    target_function="test",
                    suggested_code='return "patched"',
                )
                assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_success(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
            result = await self.executor.apply_patch(
                file_path=str(test_file),
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return "patched"',
            )
        
        assert result is True
        content = test_file.read_text()
        assert '"patched"' in content

    @pytest.mark.asyncio
    async def test_apply_patch_permission_error_during_write(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch('src.governance.executor.GovernanceExecutor._write_patch', side_effect=PermissionError):
            with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
                result = await self.executor.apply_patch(
                    file_path=str(test_file),
                    patch_type=PatchType.SECURITY,
                    target_function="test",
                    suggested_code='return "patched"',
                )
                assert result is False

    @pytest.mark.asyncio
    async def test_apply_patch_general_error_during_write(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch('src.governance.executor.GovernanceExecutor._write_patch', side_effect=RuntimeError("Write failed")):
            with patch.object(self.executor._path_validator, 'validate_path', return_value=(True, "")):
                result = await self.executor.apply_patch(
                    file_path=str(test_file),
                    patch_type=PatchType.SECURITY,
                    target_function="test",
                    suggested_code='return "patched"',
                )
                assert result is False

    def test_has_write_permission_with_os_access(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        result = self.executor._has_write_permission(test_file)
        assert result is True

    def test_has_write_permission_with_open_append(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        result = self.executor._has_write_permission(test_file)
        assert result is True

    def test_has_write_permission_no_permission(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")
        test_file.chmod(stat.S_IRUSR)
        result = self.executor._has_write_permission(test_file)
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert result is False

    def test_grant_write_permission_chmod_success(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")
        test_file.chmod(stat.S_IRUSR)
        
        result = self.executor._grant_write_permission(test_file)
        
        test_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert result is True

    def test_grant_write_permission_chmod_failure_icacls_success(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")

        with patch('pathlib.Path.chmod', side_effect=Exception("chmod failed")):
            with patch('subprocess.run', return_value=MagicMock(returncode=0)):
                result = self.executor._grant_write_permission(test_file)
                assert result is True

    def test_grant_write_permission_all_failure(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("test")

        with patch('pathlib.Path.chmod', side_effect=Exception("chmod failed")):
            with patch('subprocess.run', return_value=MagicMock(returncode=1, stderr="icacls failed")):
                result = self.executor._grant_write_permission(test_file)
                assert result is False

    def test_write_patch_target_not_found(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with pytest.raises(RuntimeError, match="Target.*not found"):
            self.executor._write_patch(
                file_path=test_file,
                patch_type=PatchType.SECURITY,
                target_function="nonexistent",
                suggested_code='return "patched"',
                required_imports=[],
            )

    def test_write_patch_syntax_error_in_generated_code(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with pytest.raises(Exception):
            self.executor._write_patch(
                file_path=test_file,
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return "unclosed',
                required_imports=[],
            )

    def test_write_patch_os_replace_fallback(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch('os.replace', side_effect=OSError("Replace failed")):
            self.executor._write_patch(
                file_path=test_file,
                patch_type=PatchType.SECURITY,
                target_function="test",
                suggested_code='return "patched"',
                required_imports=[],
            )
            content = test_file.read_text()
            assert '"patched"' in content

    def test_write_patch_os_replace_and_copy_fallback_failure(self):
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text('def test():\n    return "original"')

        with patch('os.replace', side_effect=OSError("Replace failed")):
            with patch('shutil.copy2', side_effect=Exception("Copy failed")):
                with pytest.raises(RuntimeError, match="Patch apply failed"):
                    self.executor._write_patch(
                        file_path=test_file,
                        patch_type=PatchType.SECURITY,
                        target_function="test",
                        suggested_code='return "patched"',
                        required_imports=[],
                    )
