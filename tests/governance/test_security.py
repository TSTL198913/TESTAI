from pathlib import Path

import pytest

from tests.governance.security import SecurePathValidator


class TestSecurePathValidator:
    def test_validate_allowed_path(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path(str(Path("tests/data/test.txt").resolve()))
        assert valid is True
        assert "Path validated" in msg

    def test_validate_reports_path(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path(
            str(Path("reports/test_report.html").resolve())
        )
        assert valid is True

    def test_reject_path_traversal(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path("../../etc/passwd")
        assert valid is False
        assert ("Path traversal detected" in msg) or ("not in allowed directory" in msg)

    def test_reject_absolute_path_traversal(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path("/etc/passwd")
        assert valid is False
        assert "not in allowed directory" in msg

    def test_reject_nested_path_traversal(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path("tests/../../../../../etc/passwd")
        assert valid is False
        assert ("Path traversal detected" in msg) or ("not in allowed directory" in msg)

    def test_reject_relative_path_without_base(self):
        validator = SecurePathValidator()
        valid, msg = validator.validate_path("relative/path/file.txt")
        assert valid is False
        assert ("Path must be absolute" in msg) or ("not in allowed directory" in msg)

    def test_is_sandboxed_returns_true_for_allowed(self):
        validator = SecurePathValidator()
        assert (
            validator.is_sandboxed(str(Path("tests/data/file.txt").resolve())) is True
        )

    def test_is_sandboxed_returns_false_for_traversal(self):
        validator = SecurePathValidator()
        assert validator.is_sandboxed("../../etc/passwd") is False

    def test_sanitize_path_stays_in_sandbox(self):
        validator = SecurePathValidator()
        base_dir = str(Path("tests/data").resolve())
        result = validator.sanitize_path("file.txt", base_dir)
        assert result.startswith(base_dir)

    def test_sanitize_path_rejects_escape(self):
        validator = SecurePathValidator()
        base_dir = str(Path("tests/data").resolve())
        with pytest.raises(ValueError, match="Path escapes sandbox"):
            validator.sanitize_path("../../etc/passwd", base_dir)

    def test_sanitize_path_without_base_stays_in_cwd(self):
        validator = SecurePathValidator()
        cwd = str(Path.cwd().resolve())
        result = validator.sanitize_path("tests/data/file.txt")
        assert result.startswith(cwd)

    def test_sanitize_path_rejects_escape_from_cwd(self):
        validator = SecurePathValidator()
        with pytest.raises(ValueError, match="Path escapes sandbox"):
            validator.sanitize_path("../../etc/passwd")
