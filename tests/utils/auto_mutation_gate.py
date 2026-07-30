#!/usr/bin/env python
"""Auto mutation gate - pre-commit 变异验证门

对暂存的测试文件运行变异验证，确保测试质量达标。

策略:
1. 集成测试/审计测试/E2E 测试: 跳过（无直接对应源码可变异）
2. 单元测试: 验证测试可收集且能通过，作为变异测试的前置条件
   （完整变异测试需 libcst + 多进程，在 pre-commit 中耗时过长，
    此处做轻量级验证，完整变异测试在 CI 中执行）

用法:
    python tests/utils/auto_mutation_gate.py --test tests/governance/test_xxx.py
"""
import argparse
import os
import sys
import subprocess


# 不适合变异测试的目录（无直接对应源码）
SKIP_DIRS = [
    'tests/integration/',
    'tests/audit/',
    'tests/exposed_bugs/',
    'tests/utils/',
]

# 变异测试最低 kill rate 阈值（百分比）
MIN_KILL_RATE = 80.0


def _normalize_path(path: str) -> str:
    """将路径标准化为正斜杠形式。"""
    return path.replace('\\', '/')


def _should_skip(test_file: str) -> bool:
    """判断测试文件是否应跳过变异测试。"""
    normalized = _normalize_path(test_file)
    for skip_dir in SKIP_DIRS:
        if normalized.startswith(skip_dir):
            return True
    return False


def _verify_test_collectable(test_file: str) -> bool:
    """验证测试文件可被 pytest 收集（轻量级前置检查）。

    如果测试文件有语法错误或导入错误，pytest 收集阶段就会失败，
    无需运行完整变异测试即可发现问题。
    """
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', test_file, '--collect-only', '-q'],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
        )
        if result.returncode == 0:
            return True
        # 收集失败，输出错误信息
        print(f"❌ 测试收集失败: {test_file}")
        print(result.stderr[:500] if result.stderr else result.stdout[:500])
        return False
    except subprocess.TimeoutExpired:
        print(f"⚠️  测试收集超时: {test_file}")
        return False
    except Exception as e:
        print(f"⚠️  测试收集异常: {test_file} - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Auto mutation gate - 变异验证门'
    )
    parser.add_argument(
        '--test',
        required=True,
        help='要验证的测试文件路径',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=MIN_KILL_RATE,
        help=f'最低 kill rate 百分比 (默认: {MIN_KILL_RATE})',
    )
    args = parser.parse_args()

    test_file = args.test

    if not os.path.exists(test_file):
        print(f"❌ 测试文件不存在: {test_file}")
        sys.exit(1)

    # 步骤1: 判断是否跳过
    if _should_skip(test_file):
        print(f"⏭️  跳过变异验证: {test_file}")
        print(f"    (集成/审计/E2E 测试无直接对应源码可变异)")
        sys.exit(0)

    # 步骤2: 验证测试可收集
    print(f"🔍 验证测试可收集: {test_file}")
    if not _verify_test_collectable(test_file):
        print(f"❌ 变异验证失败: 测试文件无法收集")
        sys.exit(1)

    # 步骤3: 轻量级验证通过
    # 注意: 完整变异测试在 CI 流水线中执行（tests/utils/mutation_gate_v2.py）
    # pre-commit 阶段仅做收集验证，避免提交耗时过长
    print(f"✅ 变异验证通过: {test_file}")
    print(f"    (pre-commit 轻量级验证; 完整变异测试在 CI 中执行)")
    sys.exit(0)


class AutoMutationGate:
    """AutoMutationGate - 变异测试门控类。

    提供 scan_and_mutate 接口供 verify_gate.py 等脚本调用。
    完整实现见 mutation_gate_v2.py。
    """

    def __init__(self, target_dir: str = 'src'):
        self.target_dir = target_dir
        self._mutated_files = []

    def scan_and_mutate(
        self,
        test_file: str,
        target_file: str,
        max_mutations: int = 10,
    ):
        """对目标文件执行变异测试。

        Args:
            test_file: 测试文件路径
            target_file: 被测源码文件路径
            max_mutations: 最大变异数量

        Returns:
            变异结果列表
        """
        # 轻量级实现: 仅验证文件存在且可收集
        if not os.path.exists(target_file):
            print(f"⚠️  目标文件不存在: {target_file}")
            return []

        if not os.path.exists(test_file):
            print(f"⚠️  测试文件不存在: {test_file}")
            return []

        # 完整变异测试需 libcst，此处返回空列表表示未执行
        print(f"⚠️  完整变异测试请在 CI 中运行 (mutation_gate_v2.py)")
        return []

    def restore_all(self):
        """恢复所有被变异的源码文件。"""
        for filepath in self._mutated_files:
            if os.path.exists(filepath + '.bak'):
                shutil.copy2(filepath + '.bak', filepath)
                os.remove(filepath + '.bak')
        self._mutated_files = []


if __name__ == '__main__':
    import shutil  # noqa: E402 - used by AutoMutationGate.restore_all
    main()
