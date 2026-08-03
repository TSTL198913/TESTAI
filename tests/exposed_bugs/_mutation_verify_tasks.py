"""变异测试验证: 证明 test_tasks.py 的断言有牙 (非假绿)。

方法: 临时修改 src/worker/tasks.py (备份→变异→跑测试→恢复), 验证每个变异
      是否被对应测试捕获。测试应 FAIL 才证明断言有效。

运行后自动恢复源码, 并校验恢复后内容与原文件一致。

注意: 这是临时验证脚本, 不修改任何交付代码 (src 改动会完整恢复)。
"""
import os
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SRC = ROOT / "src" / "worker" / "tasks.py"
BACKUP = ROOT / "src" / "worker" / "tasks.py.mutbak"

ORIGINAL = SRC.read_text(encoding="utf-8")


def _safe_restore(bak_path, src_path, max_retries=3):
    """安全恢复源码: copy2 + 哈希校验, 成功后删备份, 失败抛异常保留备份。

    shutil.copyfile 在 Windows 上因文件锁定可能静默失败, 导致源码残留变异。
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


def restore():
    if BACKUP.exists():
        _safe_restore(BACKUP, SRC)


def apply_mutation(find: str, replace: str) -> bool:
    """应用一处变异, 返回是否成功替换。"""
    content = SRC.read_text(encoding="utf-8")
    if find not in content:
        print(f"  [WARN] 未找到变异锚点: {find!r}")
        return False
    SRC.write_text(content.replace(find, replace, 1), encoding="utf-8")
    return True


def run_test(test_id: str) -> tuple[bool, str]:
    """运行单个测试, 返回 (passed, 摘要)。passed=True 表示测试通过 (变异未被捕获=坏)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_id, "--tb=line", "-q", "--no-header"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout + proc.stderr
    # 提取最后一行摘要
    last = ""
    for line in out.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            last = line.strip()
    return proc.returncode == 0, last


# 变异用例: (名称, 锚点, 替换, 期望失败的测试, 期望测试pass= False即捕获)
MUTATIONS = [
    {
        "name": "M1: raise e → raise ai_err (重抛治理异常而非原始异常)",
        "find": "            raise e",
        "replace": "            raise ai_err",
        "test": "tests/worker/test_tasks.py::TestWorkerBoundaryScenarios::test_run_coroutine_itself_raises_propagates_first_exception "
                "tests/worker/test_tasks.py::TestWorkerGovernancePath::test_governance_failure_reraises_original_exception",
        "expect_pass": False,  # 变异应被捕获 → 测试 FAIL
    },
    {
        "name": "M2: return gov_future.result(timeout=60) → return {'type':'mutated'} (破坏治理结果传播)",
        "find": "            return gov_future.result(timeout=60)",
        "replace": "            return {'type': 'mutated'}",
        "test": "tests/worker/test_tasks.py::TestWorkerGovernancePath::test_pipeline_exception_triggers_governance_and_returns_governed_result",
        "expect_pass": False,
    },
    {
        "name": "M3: set_trace_id(self.request.id) → set_trace_id('default') (破坏 request.id 透传契约)",
        "find": "    token = set_trace_id(self.request.id)",
        "replace": "    token = set_trace_id('default')",
        "test": "tests/worker/test_tasks.py::TestWorkerBoundaryScenarios::test_none_request_id_passed_through_to_set_trace_id",
        "expect_pass": False,
    },
    {
        "name": "M4: future.result(timeout=60) → future.result(timeout=10) (破坏超时契约)",
        "find": "        future = AsyncLoopManager.run_coroutine(_execute())\n        return future.result(timeout=60)",
        "replace": "        future = AsyncLoopManager.run_coroutine(_execute())\n        return future.result(timeout=10)",
        "test": "tests/worker/test_tasks.py::TestWorkerNormalPath::test_normal_path_returns_result_and_calls_run_coroutine_once",
        "expect_pass": False,
    },
]


def main():
    shutil.copyfile(SRC, BACKUP)
    results = []
    try:
        for m in MUTATIONS:
            restore_via_backup()
            ok = apply_mutation(m["find"], m["replace"])
            if not ok:
                results.append((m["name"], "SKIP", "锚点未找到"))
                continue
            passed, summary = run_test(m["test"])
            captured = (passed == m["expect_pass"])  # 期望False, 实际False → 捕获成功
            status = "CAPTURED ✅" if (not passed and not m["expect_pass"]) else "ESCAPED ❌"
            results.append((m["name"], status, summary))
    finally:
        restore_via_backup()

    # 最终校验: 源码必须与原始完全一致
    final = SRC.read_text(encoding="utf-8")
    restored_ok = final == ORIGINAL

    print("\n" + "=" * 70)
    print("变异测试结果 (测试应 FAIL 才证明有牙):")
    print("=" * 70)
    for name, status, summary in results:
        print(f"\n[{status}] {name}")
        print(f"   pytest: {summary}")
    print("\n" + "=" * 70)
    print(f"源码恢复校验: {'✅ 完全一致' if restored_ok else '❌ 不一致! 源码被污染!'}")
    print("=" * 70)

    all_captured = all(s == "CAPTURED ✅" for _, s, _ in results) and restored_ok
    sys.exit(0 if all_captured else 1)


def restore_via_backup():
    if BACKUP.exists():
        _safe_restore(BACKUP, SRC)


if __name__ == "__main__":
    main()
