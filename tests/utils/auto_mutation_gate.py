#!/usr/bin/env python3
"""
自动变异验证门 - Trae测试提交后的自动评估器

Trae提交测试后，自动对被测代码注入变异，计算kill rate，
低于80%则自动拒绝并触发重写。

使用方式：
    python tests/utils/auto_mutation_gate.py --test tests/governance/test_transformer_new.py

输出：
    - Kill rate 评分
    - 详细评估报告
    - 通过/拒绝结论
"""
import argparse
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MutationResult:
    mutant_id: str
    file: str
    line: int
    mutation_type: str
    killed: bool
    test_name: str = ""


@dataclass
class GateResult:
    passed: bool
    kill_rate: float
    total_mutants: int
    killed_mutants: int
    results: List[MutationResult] = field(default_factory=list)
    message: str = ""


@contextmanager
def backup_and_restore(filepath):
    import tempfile
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.mutant_bak') as tmp:
        backup_path = tmp.name
        with open(filepath, 'rb') as f:
            tmp.write(f.read())
    
    original_content = None
    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    try:
        yield
    finally:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(original_content)
            
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception as e:
            print(f"[WARN] 恢复文件失败: {e}")
            if os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, filepath)
                    os.remove(backup_path)
                except:
                    print(f"⚠️ 备用恢复也失败，备份文件: {backup_path}")


class MutantGenerator:
    """变异生成器 - 对代码注入各种变异"""

    def __init__(self, source_file: str):
        self.source_file = source_file
        self.mutants = []

    def generate_mutants(self) -> List[MutationResult]:
        with open(self.source_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.split("\n")
        mutants = []
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            if "self.patched = True" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-P",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="patched_flag",
                    killed=False
                ))
            
            if "class_match =" in line and "target_class" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-C",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="class_match",
                    killed=False
                ))
            
            if "is_governance_processor" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-G",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="governance_check",
                    killed=False
                ))
            
            if "if not transformer.patched" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-V",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="validity_check",
                    killed=False
                ))
            
            if "return" in line and "True" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-B",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="boolean_true",
                    killed=False
                ))
            
            if "return" in line and "False" in line:
                mutants.append(MutationResult(
                    mutant_id=f"M-{line_num:04d}-F",
                    file=os.path.basename(self.source_file),
                    line=line_num,
                    mutation_type="boolean_false",
                    killed=False
                ))
        
        return mutants

    def apply_mutant(self, mutant: MutationResult):
        with open(self.source_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.split("\n")
        
        if mutant.mutation_type == "patched_flag":
            content = content.replace("self.patched = True", "# [MUTANT] self.patched = True")
        
        elif mutant.mutation_type == "class_match":
            content = content.replace(
                "class_match = (self.target_class is None or self.current_class == self.target_class)",
                "# [MUTANT] class_match always True\nclass_match = True"
            )
        
        elif mutant.mutation_type == "governance_check":
            content = content.replace(
                'is_governance_processor = processor.__class__.__name__ == "GovernanceProcessor"',
                '# [MUTANT] wrong name\nis_governance_processor = processor.__class__.__name__ == "WrongProcessor"'
            )
        
        elif mutant.mutation_type == "validity_check":
            content = content.replace(
                "if not transformer.patched:",
                "# [MUTANT] skip check\nif False:"
            )
        
        elif mutant.mutation_type == "boolean_true":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            content = "\n".join(lines)
        
        elif mutant.mutation_type == "boolean_false":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("False", "True")
            content = "\n".join(lines)
        
        with open(self.source_file, "w", encoding="utf-8") as f:
            f.write(content)


class MutationGate:
    """变异验证门 - 评估测试有效性"""

    def __init__(self, test_file: str, source_file: Optional[str] = None):
        self.test_file = test_file
        self.source_file = source_file or self._infer_source_file(test_file)
        self.kill_rate_threshold = 0.8

    def _infer_source_file(self, test_file: str) -> str:
        test_dir = os.path.dirname(test_file)
        if "governance" in test_dir:
            return os.path.join("src", "governance", "transformer.py")
        elif "engine" in test_dir:
            return os.path.join("src", "engine", "pipeline.py")
        return os.path.join("src", "governance", "transformer.py")

    def run(self) -> GateResult:
        print(f"[LAUNCH] 启动变异验证门")
        print(f"  测试文件: {self.test_file}")
        print(f"  源文件: {self.source_file}")
        print(f"  Kill rate阈值: {self.kill_rate_threshold * 100:.0f}%")
        print()

        generator = MutantGenerator(self.source_file)
        mutants = generator.generate_mutants()

        if not mutants:
            return GateResult(
                passed=False,
                kill_rate=0.0,
                total_mutants=0,
                killed_mutants=0,
                message="未生成任何变异点"
            )

        print(f"[MUTATE] 生成了 {len(mutants)} 个变异点")
        print()

        killed_count = 0
        results = []

        with backup_and_restore(self.source_file):
            for mutant in mutants:
                print(f"  变异点: {mutant.mutant_id}")
                print(f"    位置: {mutant.file}:{mutant.line}")
                print(f"    类型: {mutant.mutation_type}")

                generator.apply_mutant(mutant)

                result = subprocess.run(
                    ["python", "-m", "pytest", self.test_file, "-v", "--tb=short", "--no-header"],
                    capture_output=True, text=True, timeout=60
                )

                if result.returncode != 0:
                    mutant.killed = True
                    killed_count += 1
                    print("    [PASS] 已杀死（测试失败）")
                else:
                    mutant.killed = False
                    print("    [FAIL] 存活（测试通过）")
                
                results.append(mutant)
                print()

        kill_rate = killed_count / len(mutants)
        passed = kill_rate >= self.kill_rate_threshold

        message = ""
        if passed:
            message = f"[PASS] 验证通过！Kill rate: {kill_rate * 100:.1f}% ≥ {self.kill_rate_threshold * 100:.0f}%"
        else:
            message = f"[FAIL] 验证失败！Kill rate: {kill_rate * 100:.1f}% < {self.kill_rate_threshold * 100:.0f}%"

        return GateResult(
            passed=passed,
            kill_rate=kill_rate,
            total_mutants=len(mutants),
            killed_mutants=killed_count,
            results=results,
            message=message
        )


def format_report(result: GateResult) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("变异验证门评估报告")
    lines.append("=" * 70)
    lines.append("")

    lines.append(f"结论: {'[PASS] 通过' if result.passed else '[FAIL] 拒绝'}")
    lines.append(f"Kill Rate: {result.kill_rate * 100:.1f}%")
    lines.append(f"总变异点: {result.total_mutants}")
    lines.append(f"被杀死: {result.killed_mutants}")
    lines.append(f"存活: {result.total_mutants - result.killed_mutants}")
    lines.append("")

    lines.append("详细结果:")
    for mutant in result.results:
        status = "[PASS] 已杀死" if mutant.killed else "[FAIL] 存活"
        lines.append(f"  {mutant.mutant_id} | {mutant.file}:{mutant.line} | {mutant.mutation_type} | {status}")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="自动变异验证门")
    parser.add_argument("--test", required=True, help="测试文件路径")
    parser.add_argument("--source", help="源文件路径（可选，自动推断）")
    parser.add_argument("--threshold", type=float, default=0.8, help="Kill rate阈值")
    args = parser.parse_args()

    gate = MutationGate(args.test, args.source)
    gate.kill_rate_threshold = args.threshold

    result = gate.run()
    print(format_report(result))

    if not result.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()