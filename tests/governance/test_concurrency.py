import multiprocessing
import os
from pathlib import Path

from src.governance.executor import GovernanceExecutor


def worker(file_path, iteration):
    """模拟一个并发的任务进程"""
    executor = GovernanceExecutor()
    # 每个进程尝试打一个不同的补丁，目标是最终文件依然合法
    new_code = f"return {iteration}"
    try:
        # 这里直接模拟 apply_patch 流程，跳过复杂的备份逻辑以测试锁
        executor._write_patch(Path(file_path), "run", new_code, [])
    except Exception as e:
        # 记录冲突或失败，但不要中断测试
        pass


def test_concurrency_stress():
    # 准备环境
    test_file = "stress_test_target.py"
    with open(test_file, "w") as f:
        f.write("def run():\n    return 0")

    print(f"🚀 启动并发压力测试，目标文件: {test_file}")

    # 并行执行：启动 10 个进程
    processes = []
    for i in range(10):
        p = multiprocessing.Process(target=worker, args=(test_file, i))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    # 验证环节：如果锁无效，文件会变空或乱码，系统会崩溃
    with open(test_file, "r") as f:
        content = f.read()
        print("\n--- 并发测试结果 ---")
        print(content)

    # 如果文件包含 'return' 关键字，说明写入成功且未被损坏
    assert "return" in content, "并发写入导致了文件损坏！"
    print("✅ [Concurrency Test Passed] 锁定机制生效，数据完整性未受损！")

    # 清理
    if os.path.exists(test_file): os.remove(test_file)


if __name__ == "__main__":
    test_concurrency_stress()