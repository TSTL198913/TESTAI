"""平台层变异 spot-check: 验证 API 端点的关键断言。
运行: python -m pytest tests/platform/_mutation_verify_platform.py -v --timeout=60
"""
import os
import shutil
import subprocess
import sys

import pytest

API_FILE = os.path.join("src", "platform", "api.py")

# (变异名, 查找, 替换, 期望关键字)
MUTATIONS = [
    (
        "P1: Alert 404 → 200 (错误响应被误认为成功)",
        'raise HTTPException(status_code=404, detail="Alert not found")',
        'raise HTTPException(status_code=200, detail="Alert not found")',
        ["404", "Alert not found", "test_alert"],
    ),
    (
        "P2: 移除 is_expired 检查 (过期审批被允许通过)",
        "if record.is_expired:",
        "if False and record.is_expired:",
        ["is_expired", "expired", "test_approval"],
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
    bak = _backup_path(API_FILE)
    if os.path.exists(bak):
        _safe_restore(bak, API_FILE)


def _run_platform_tests():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/platform/test_api.py",
         "-q", "--tb=line", "--timeout=60", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _restore_all()


@pytest.mark.parametrize("mut_name,find,replace,keywords", MUTATIONS)
def test_platform_mutation_caught(mut_name, find, replace, keywords):
    original = _read(API_FILE)
    assert find in original, f"变异 {mut_name}: 查找字符串不存在"

    bak = _backup_path(API_FILE)
    shutil.copy2(API_FILE, bak)
    mutated = original.replace(find, replace, 1)
    _write(API_FILE, mutated)

    try:
        exit_code, output = _run_platform_tests()
    finally:
        _restore_all()

    assert exit_code != 0, (
        f"变异 {mut_name} 未被任何平台测试捕获 — 假绿!\n"
        f"变异: {find!r} → {replace!r}\n"
        f"输出:\n{output[-400:]}"
    )

    output_lower = output.lower()
    caught = [kw for kw in keywords if kw.lower() in output_lower]
    assert len(caught) > 0, (
        f"变异 {mut_name} 虽导致失败, 但未匹配预期关键字 {keywords}\n"
        f"输出:\n{output[-400:]}"
    )


def test_no_mutbak_leftover():
    _restore_all()
    assert not os.path.exists(_backup_path(API_FILE))
