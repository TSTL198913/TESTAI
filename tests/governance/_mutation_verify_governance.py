"""治理层变异 spot-check: 快速验证 3 个关键断言的 kill rate。

仅验证最关键的分类/审批逻辑, 不全量变异 (节省时间)。
运行: python -m pytest tests/governance/_mutation_verify_governance.py -v --timeout=60
"""
import os
import shutil
import subprocess
import sys

import pytest

ORCH_FILE = os.path.join("src", "governance", "orchestrator.py")
APPROVAL_FILE = os.path.join("src", "governance", "approval.py")

# (变异名, 文件, 查找, 替换, 期望被哪个测试关键字捕获)
MUTATIONS = [
    (
        "G1: _classify_exception 'typeerror' → 'typerror' (大小写敏感性破坏)",
        ORCH_FILE,
        '"typeerror"',
        '"typerror"',
        ["AI_DIAGNOSE", "test_classify_exception_code_error"],
    ),
    (
        "G2: _classify_exception 'assertionerror' → 'asertionerror' (覆盖率缺口验证)",
        ORCH_FILE,
        '"assertionerror"',
        '"asertionerror"',
        ["AI_DIAGNOSE", "test_classify_exception_code_error"],
    ),
    (
        "G3: requires_approval 移除 'refactoring' 判断 (审批闸门绕过)",
        APPROVAL_FILE,
        "if self.proposal.patch_type.value in ['security', 'refactoring']:",
        "if self.proposal.patch_type.value in ['security']:",
        ["requires_approval", "refactoring", "test_requires_approval"],
    ),
    (
        "G4: requires_approval 移除 'security' 判断 (安全补丁自动批准)",
        APPROVAL_FILE,
        "if self.proposal.patch_type.value in ['security', 'refactoring']:",
        "if self.proposal.patch_type.value in ['performance']:",
        ["requires_approval", "security", "test_requires_approval"],
    ),
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _backup_path(path):
    return path + ".mutbak"


def _safe_restore(bak_path, src_path, max_retries=3):
    """安全恢复源码: copy2 + 哈希校验, 成功后删备份, 失败抛异常保留备份。

    shutil.move 在 Windows 上因文件锁定可能静默失败, 导致源码残留变异。
    改为先 copy2 再哈希校验, 确保恢复成功后才删除备份。
    """
    import hashlib
    import time

    with open(bak_path, "rb") as f:
        bak_hash = hashlib.md5(f.read()).hexdigest()

    last_err = None
    for attempt in range(max_retries):
        try:
            shutil.copy2(bak_path, src_path)
            with open(src_path, "rb") as f:
                src_hash = hashlib.md5(f.read()).hexdigest()
            if src_hash == bak_hash:
                os.remove(bak_path)
                return
            last_err = RuntimeError(
                f"哈希校验失败: bak={bak_hash} src={src_hash}"
            )
        except (OSError, IOError) as e:
            last_err = e
        time.sleep(0.3 * (attempt + 1))

    raise RuntimeError(
        f"恢复源码失败 ({max_retries} 次重试): {src_path} <- {bak_path}\n"
        f"备份文件已保留, 请手动恢复。\n"
        f"最后错误: {last_err}"
    )


def _restore_all():
    for _, path, _, _, _ in MUTATIONS:
        bak = _backup_path(path)
        if os.path.exists(bak):
            _safe_restore(bak, path)


def _run_governance_tests():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/governance/test_orchestrator.py",
         "tests/governance/test_approval.py",
         "-q", "--tb=line", "--timeout=60", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _restore_all()


@pytest.mark.parametrize("mut_name,file_path,find,replace,keywords", MUTATIONS)
def test_governance_mutation_caught(mut_name, file_path, find, replace, keywords):
    """治理层关键变异必须被现有测试捕获。"""
    original = _read(file_path)

    assert find in original, (
        f"变异 {mut_name}: 查找字符串不存在于 {file_path}"
    )

    bak = _backup_path(file_path)
    shutil.copy2(file_path, bak)
    mutated = original.replace(find, replace, 1)
    _write(file_path, mutated)

    try:
        exit_code, output = _run_governance_tests()
    finally:
        _restore_all()

    assert exit_code != 0, (
        f"变异 {mut_name} 未被任何治理测试捕获 — 假绿!\n"
        f"变异: {find!r} → {replace!r}\n"
        f"输出:\n{output[-500:]}"
    )

    output_lower = output.lower()
    caught = [kw for kw in keywords if kw.lower() in output_lower]
    assert len(caught) > 0, (
        f"变异 {mut_name} 虽导致失败, 但未匹配预期关键字 {keywords}\n"
        f"输出:\n{output[-500:]}"
    )


def test_no_mutbak_leftover():
    _restore_all()
    for _, path, _, _, _ in MUTATIONS:
        bak = _backup_path(path)
        assert not os.path.exists(bak), f"遗留备份: {bak}"
