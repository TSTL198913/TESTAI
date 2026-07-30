"""BUG-006: SecurePathValidator 路径校验失效 + ALLOWED_DIRS 子串匹配越权。

源码位置:src/governance/security.py:7-42 SecurePathValidator.validate_path

根因(已修复):
1. L25 `path = Path(target_path).resolve()` —— 先 resolve
2. L30 `if ".." in str(path): return False` —— resolve 后 .. 已被解析,这个检查永不触发(死代码)
3. L33-37 遍历 path.parts,只要路径中包含 tests/reports/data/output/src 任一目录名就放行
4. 攻击向量:/etc/tests/passwd、/etc/data/shadow 等含 ALLOWED_DIRS 关键字的越权路径会通过校验

修复方案:
- .. 检查移到 resolve() 之前(基于原始 Path.parts)
- 用 path.relative_to(project_root) 做前缀匹配,替代子串匹配
- 显式 project_root 参数,避免依赖 Path.cwd() 不可控
"""
import os
import pytest

from src.governance.security import SecurePathValidator


@pytest.mark.parametrize(
    "malicious_path,allowed_dir",
    [
        ("/etc/tests/passwd", "tests"),
        ("/etc/data/shadow", "data"),
        ("/etc/output/evil", "output"),
        ("/etc/src/passwd", "src"),
        ("/tmp/reports/malicious", "reports"),
    ],
)
def test_malicious_paths_with_allowed_dir_keyword_rejected(malicious_path, allowed_dir):
    """含 ALLOWED_DIRS 关键字但实际越权的路径必须被拒绝。

    正确行为:/etc/tests/passwd 等路径不在项目目录内,应返回 (False, ...)。
    旧实现:parts 含 'tests',返回 (True, ...),导致沙箱越权。
    """
    validator = SecurePathValidator()
    is_valid, msg = validator.validate_path(malicious_path)

    assert is_valid is False, (
        f"路径 {malicious_path} 含 ALLOWED_DIRS 关键字 '{allowed_dir}' 但实际越权,应被拒绝。"
        f"当前实现因子串匹配放行, 实际 is_valid={is_valid}, msg={msg}"
    )


def test_path_with_traversal_syntax_rejected_even_if_resolves_to_allowed_dir():
    """含 .. 的路径应被拒绝,即使 resolve 后落在 ALLOWED_DIRS 内。

    正确行为:原始路径含 .. 就应拒绝(防御性校验)。
    旧实现:先 resolve 再检查 ..,.. 已被解析,检查永不触发。
    """
    validator = SecurePathValidator()
    # /etc/tests/../tests/passwd
    # resolve 后:/etc/tests/passwd,含 'tests',旧实现返回 True
    # 但原始路径含 ..,应被拒绝
    target = "/etc/tests/../tests/passwd"
    is_valid, msg = validator.validate_path(target)

    assert is_valid is False, (
        f"含 .. 的路径应被拒绝(路径遍历),旧实现因 resolve() 后 .. 被解析而放行, "
        f"is_valid={is_valid}, msg={msg}"
    )


def test_validator_checks_path_prefix_not_substring():
    """路径校验应检查是否在项目目录前缀内,而非检查 parts 是否含 ALLOWED_DIRS。

    正确行为:应有项目根目录约束,如 /workspace/TestAI/src/... 才放行。
    旧实现:任何含 'src'/'tests'/'data' 等关键字的绝对路径都放行。
    """
    validator = SecurePathValidator()

    # /var/log/src/passwd 含 'src' 但明显不在项目内
    is_valid, _ = validator.validate_path("/var/log/src/passwd")

    assert is_valid is False, (
        f"/var/log/src/passwd 不在项目目录内,应被拒绝。"
        f"旧实现因 parts 含 'src' 而放行, 实际 is_valid={is_valid}"
    )


# ============ 修复后新增正向测试 ============

def test_validates_real_project_subdir():
    """合法路径:项目根下 src/ 子目录的文件应通过校验。"""
    project_root = os.path.abspath(".")
    validator = SecurePathValidator(project_root=project_root)
    valid_path = os.path.join(project_root, "src", "governance", "transformer.py")

    is_valid, msg = validator.validate_path(valid_path)
    assert is_valid is True, (
        f"项目根下 src/ 子目录的合法路径应通过校验, 实际 is_valid={is_valid}, msg={msg}"
    )


def test_rejects_path_in_wrong_subdir():
    """项目根下不在 ALLOWED_DIRS 中的子目录应被拒绝。"""
    project_root = os.path.abspath(".")
    validator = SecurePathValidator(project_root=project_root)
    # docs/ 不在 ALLOWED_DIRS 中
    invalid_path = os.path.join(project_root, "docs", "foo.md")

    is_valid, msg = validator.validate_path(invalid_path)
    assert is_valid is False, (
        f"项目根下 docs/ 子目录不在 ALLOWED_DIRS 中,应被拒绝, "
        f"实际 is_valid={is_valid}, msg={msg}"
    )


def test_project_root_from_env(monkeypatch):
    """PROJECT_ROOT 环境变量应被读取。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # 在临时项目根下创建 src/ 子目录
        src_dir = os.path.join(tmpdir, "src")
        os.makedirs(src_dir)
        target_file = os.path.join(src_dir, "foo.py")
        with open(target_file, "w") as f:
            f.write("# test")

        monkeypatch.setenv("PROJECT_ROOT", tmpdir)
        validator = SecurePathValidator()

        is_valid, msg = validator.validate_path(target_file)
        assert is_valid is True, (
            f"PROJECT_ROOT 环境变量指向的目录下 src/ 文件应通过校验, "
            f"实际 is_valid={is_valid}, msg={msg}"
        )


def test_rejects_non_string_path():
    """非字符串路径应被拒绝。"""
    validator = SecurePathValidator()
    is_valid, msg = validator.validate_path(None)
    assert is_valid is False
    assert "string" in msg.lower()


def test_rejects_null_byte_injection():
    """NULL 字节注入应被拒绝。"""
    validator = SecurePathValidator()
    is_valid, msg = validator.validate_path("src/foo.py\x00.evil")
    assert is_valid is False
    assert "null" in msg.lower()
