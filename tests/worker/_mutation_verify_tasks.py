"""变异测试验证: 确认 test_tasks.py 的断言能捕获 tasks.py 的真实 bug。

方法: 对 tasks.py 注入针对性变异, 运行 test_tasks.py, 验证测试失败 (捕获变异)。
每个变异后立即恢复原文件, 确保 src/ 不被污染。

运行: python -m pytest tests/worker/_mutation_verify_tasks.py -v --timeout=120
"""
import os
import shutil
import subprocess
import sys

import pytest

TASKS_PY = os.path.join("src", "worker", "tasks.py")
BACKUP = TASKS_PY + ".mutbak"

# (变异名, 查找, 替换, 期望失败的测试关键字列表)
# 每个变异必须至少被一个测试捕获, 否则该测试是假绿。
MUTATIONS = [
    (
        "M1: timeout=60 → timeout=30 (正常路径)",
        "future.result(timeout=60)",
        "future.result(timeout=30)",
        ["timeout=60", "test_normal_path"],
    ),
    (
        "M2: raise e → raise ai_err (异常归并语义)",
        "            raise e",
        "            raise ai_err",
        ["Pipeline exploded", "test_governance_failure_reraises"],
    ),
    (
        "M3: gov_future.result(timeout=60) → timeout=30 (治理路径)",
        "gov_future.result(timeout=60)",
        "gov_future.result(timeout=30)",
        ["timeout=60", "test_pipeline_exception_triggers"],
    ),
    (
        "M4: 删除 finally reset_trace_id (trace_id 泄漏)",
        "    finally:\n        reset_trace_id(token)",
        "    finally:\n        pass  # reset_trace_id removed",
        ["reset", "test_trace_id_reset"],
    ),
    (
        "M5: set_trace_id(self.request.id) → set_trace_id(None) (trace_id 断链)",
        "token = set_trace_id(self.request.id)",
        "token = set_trace_id(None)",
        ["test-task-id-001", "test_normal_path", "assert_called_once_with"],
    ),
    (
        "M6: return gov_future.result → return None (治理结果丢弃)",
        "            return gov_future.result(timeout=60)",
        "            return None  # governance result discarded",
        ["test_pipeline_exception_triggers", "result is"],
    ),
]


def _read_original():
    with open(TASKS_PY, "r", encoding="utf-8") as f:
        return f.read()


def _write(content):
    with open(TASKS_PY, "w", encoding="utf-8") as f:
        f.write(content)


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


def _restore():
    if os.path.exists(BACKUP):
        _safe_restore(BACKUP, TASKS_PY)


def _run_tests():
    """运行 test_tasks.py, 返回 (exit_code, stdout)。"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/worker/test_tasks.py",
         "-q", "--tb=line", "--timeout=60", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(autouse=True)
def _ensure_restore():
    """确保每个测试后恢复原文件, 即使测试失败。"""
    yield
    _restore()


@pytest.mark.parametrize("mutation_name, find, replace, expected_keywords", MUTATIONS)
def test_mutation_is_caught(mutation_name, find, replace, expected_keywords):
    """每个变异必须被 test_tasks.py 捕获 (测试失败), 否则该测试是假绿。"""
    original = _read_original()

    # 验证查找字符串存在 (否则变异无意义)
    assert find in original, (
        f"变异 {mutation_name}: 查找字符串不存在于 tasks.py, 可能源码已变更:\n{find!r}"
    )

    # 备份并应用变异
    shutil.copy2(TASKS_PY, BACKUP)
    mutated = original.replace(find, replace, 1)
    _write(mutated)

    # 运行测试
    exit_code, output = _run_tests()

    # 恢复原文件
    _restore()

    # 变异必须导致测试失败 (exit_code != 0)
    assert exit_code != 0, (
        f"变异 {mutation_name} 未被任何测试捕获 — 测试是假绿!\n"
        f"变异内容: {find!r} → {replace!r}\n"
        f"测试输出:\n{output[-500:]}"
    )

    # 验证期望的测试确实失败 (输出中包含关键字)
    output_lower = output.lower()
    caught_by = [kw for kw in expected_keywords if kw.lower() in output_lower]
    assert len(caught_by) > 0, (
        f"变异 {mutation_name} 虽导致测试失败, 但未匹配预期测试关键字 {expected_keywords}\n"
        f"输出:\n{output[-800:]}"
    )


def test_no_mutbak_leftover():
    """验证变异测试后没有遗留 .mutbak 文件。"""
    _restore()
    assert not os.path.exists(BACKUP), f"遗留备份文件: {BACKUP}"
