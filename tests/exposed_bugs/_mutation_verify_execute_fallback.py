"""变异测试验证: /execute 同步治理回退断言有牙 (非假绿)。

方法: 临时修改 src/platform/api.py (备份→变异→跑测试→恢复), 验证每个变异
      是否被对应测试捕获。测试应 FAIL 才证明断言有效。

M5: broker 不可用分支不接 (空 tuple) → broker 异常落 TASK_SUBMISSION_FAILED
M6: 回退分支不调 apply 直接声称成功 (跳过治理) → 治理闭环未触发

运行后自动恢复源码, 并校验恢复后内容与原文件一致。
临时验证脚本, 不修改任何交付代码 (src 改动完整恢复)。
"""
import os
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SRC = ROOT / "src" / "platform" / "api.py"
BACKUP = ROOT / "src" / "platform" / "api.py.mutbak"

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


def restore_via_backup():
    if BACKUP.exists():
        _safe_restore(BACKUP, SRC)


def apply_mutation(find: str, replace: str) -> bool:
    content = SRC.read_text(encoding="utf-8")
    if find not in content:
        print(f"  [WARN] 未找到变异锚点: {find[:60]!r}...")
        return False
    SRC.write_text(content.replace(find, replace, 1), encoding="utf-8")
    return True


def run_test(test_id: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_id, "--tb=line", "-q", "--no-header"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180,
    )
    out = proc.stdout + proc.stderr
    last = ""
    for line in out.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            last = line.strip()
    return proc.returncode == 0, last


MUTATIONS = [
    {
        "name": "M5: _BROKER_UNAVAILABLE_EXC=() (broker 分支不接, 落 TASK_SUBMISSION_FAILED)",
        "find": "_BROKER_UNAVAILABLE_EXC = tuple(\n    t for t in [_KombuOperationalError, _RedisConnectionError] if t is not None\n)",
        "replace": "_BROKER_UNAVAILABLE_EXC = ()  # M5 mutation",
        "test": "tests/exposed_bugs/test_bug_execute_sync_governance_fallback.py::TestExecuteSyncFallbackWiring::test_broker_unavailable_triggers_sync_apply_and_returns_governance_result",
        "expect_pass": False,
    },
    {
        "name": "M6: 回退分支不调 apply, 直接声称成功 (跳过治理闭环)",
        "find": (
            "            eager_result = await run_in_threadpool(\n"
            "                run_test_pipeline.apply, (request_dict,)\n"
            "            )\n"
            "            if eager_result.successful():\n"
            "                return ApiResponse(\n"
            "                    success=True,\n"
            "                    data={\n"
            '                        "status": "completed_sync",\n'
            '                        "trace_id": trace_id,\n'
            '                        "result": eager_result.result,\n'
            '                        "fallback": "sync",\n'
            "                    },\n"
            '                    message="Broker 不可用, 已同步执行 pipeline+治理闭环",\n'
            "                )\n"
            "            # 任务体重抛异常 (pipeline + 治理均失败) → 包装为失败响应\n"
            "            raise eager_result.result"
        ),
        "replace": (
            "            # M6 mutation: 不调 apply, 直接声称成功 (跳过治理闭环)\n"
            "            return ApiResponse(\n"
            "                success=True,\n"
            '                data={"status": "completed_sync", "trace_id": trace_id,\n'
            '                      "result": {"status": "SKIPPED_NO_GOVERNANCE"}, "fallback": "sync"},\n'
            '                message="Broker 不可用, 已同步执行 pipeline+治理闭环",\n'
            "            )"
        ),
        "test": "tests/exposed_bugs/test_bug_execute_sync_governance_fallback.py::TestExecuteSyncFallbackRealGovernance::test_sync_fallback_actually_triggers_governance_closed_loop",
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
            status = "CAPTURED ✅" if (not passed and not m["expect_pass"]) else "ESCAPED ❌"
            results.append((m["name"], status, summary))
    finally:
        restore_via_backup()

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


if __name__ == "__main__":
    main()
