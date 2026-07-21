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

    with tempfile.NamedTemporaryFile(
        mode="wb", delete=False, suffix=".mutant_bak"
    ) as tmp:
        backup_path = tmp.name
        with open(filepath, "rb") as f:
            tmp.write(f.read())

    original_content = None
    with open(filepath, "r", encoding="utf-8") as f:
        original_content = f.read()

    try:
        yield
    finally:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
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
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-P",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="patched_flag",
                        killed=False,
                    )
                )

            if "self.patched = False" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-PF",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="patched_flag_init",
                        killed=False,
                    )
                )

            if "class_match =" in line and "target_class" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-C",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="class_match",
                        killed=False,
                    )
                )

            if "is_governance_processor" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-G",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="governance_check",
                        killed=False,
                    )
                )

            if "if not transformer.patched" in line or "getattr(transformer, \"patched\"" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-V",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="validity_check",
                        killed=False,
                    )
                )

            if "with_changes(body=" in line and "IndentedBlock" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-WC",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="with_changes",
                        killed=False,
                    )
                )

            if "return" in line and "True" in line and not line.strip().startswith("#"):
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-B",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="boolean_true",
                        killed=False,
                    )
                )

            if "return" in line and "False" in line and not line.strip().startswith("#"):
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-F",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="boolean_false",
                        killed=False,
                    )
                )

            if "requires_approval" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-RA",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="requires_approval",
                        killed=False,
                    )
                )

            if "self.locked" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-L",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="locked_flag",
                        killed=False,
                    )
                )

            if "self.approved" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-A",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="approved_flag",
                        killed=False,
                    )
                )

            if "is_valid" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-IV",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="is_valid",
                        killed=False,
                    )
                )

            if "confidence_score" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-CS",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="confidence_score",
                        killed=False,
                    )
                )

            if "==" in line and "self._events" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-CE",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="collection_equal",
                        killed=False,
                    )
                )

            if "self._events" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-EV",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="events_access",
                        killed=False,
                    )
                )

            if "trace_id" in line and "==" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-TI",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="trace_id_match",
                        killed=False,
                    )
                )

            if "action_type" in line and "==" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-AT",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="action_type_match",
                        killed=False,
                    )
                )

            if "component" in line and "==" in line:
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-CO",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="component_match",
                        killed=False,
                    )
                )

            if "success" in line and "=" in line and not line.strip().startswith("#"):
                if "success=True" in line:
                    mutants.append(
                        MutationResult(
                            mutant_id=f"M-{line_num:04d}-ST",
                            file=os.path.basename(self.source_file),
                            line=line_num,
                            mutation_type="success_true",
                            killed=False,
                        )
                    )
                elif "success=False" in line:
                    mutants.append(
                        MutationResult(
                            mutant_id=f"M-{line_num:04d}-SF",
                            file=os.path.basename(self.source_file),
                            line=line_num,
                            mutation_type="success_false",
                            killed=False,
                        )
                    )

            if "use_fallback" in line and "=" in line and not line.strip().startswith("#"):
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-UF",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="use_fallback",
                        killed=False,
                    )
                )

            if "total_generated" in line and "=" in line and not line.strip().startswith("#"):
                mutants.append(
                    MutationResult(
                        mutant_id=f"M-{line_num:04d}-TG",
                        file=os.path.basename(self.source_file),
                        line=line_num,
                        mutation_type="total_generated",
                        killed=False,
                    )
                )

            if "fallback_used" in line and "=" in line and not line.strip().startswith("#"):
                if "fallback_used=True" in line:
                    mutants.append(
                        MutationResult(
                            mutant_id=f"M-{line_num:04d}-FB",
                            file=os.path.basename(self.source_file),
                            line=line_num,
                            mutation_type="fallback_used",
                            killed=False,
                        )
                    )

        return mutants

    def apply_mutant(self, mutant: MutationResult):
        with open(self.source_file, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")

        if mutant.mutation_type == "patched_flag":
            content = content.replace(
                "self.patched = True", "# [MUTANT] self.patched = True"
            )

        elif mutant.mutation_type == "patched_flag_init":
            content = content.replace(
                "self.patched = False", "# [MUTANT] patched always True\nself.patched = True"
            )

        elif mutant.mutation_type == "class_match":
            content = content.replace(
                "class_match = (self.target_class is None or self.current_class == self.target_class)",
                "# [MUTANT] class_match always True\nclass_match = True",
            )

        elif mutant.mutation_type == "governance_check":
            content = content.replace(
                'is_governance_processor = processor.__class__.__name__ == "GovernanceProcessor"',
                '# [MUTANT] wrong name\nis_governance_processor = processor.__class__.__name__ == "WrongProcessor"',
            )

        elif mutant.mutation_type == "validity_check":
            if "if not transformer.patched" in content:
                content = content.replace(
                    "if not transformer.patched:", "# [MUTANT] skip check\nif False:"
                )
            elif 'getattr(transformer, "patched"' in content:
                content = content.replace(
                    'getattr(transformer, "patched", False)',
                    '# [MUTANT] always True\nTrue',
                )

        elif mutant.mutation_type == "with_changes":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace(
                "return updated_node",
                "# [MUTANT] skip change\nreturn original_node"
            )
            content = "\n".join(lines)

        elif mutant.mutation_type == "boolean_true":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            content = "\n".join(lines)

        elif mutant.mutation_type == "boolean_false":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("False", "True")
            content = "\n".join(lines)

        elif mutant.mutation_type == "requires_approval":
            if "return" in lines[mutant.line - 1] and "True" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            elif "return" in lines[mutant.line - 1] and "False" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace("False", "True")
            content = "\n".join(lines)

        elif mutant.mutation_type == "locked_flag":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            content = "\n".join(lines)

        elif mutant.mutation_type == "approved_flag":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            content = "\n".join(lines)

        elif mutant.mutation_type == "is_valid":
            if "return" in lines[mutant.line - 1] and "True" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace("True", "False")
            elif "return" in lines[mutant.line - 1] and "False" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace("False", "True")
            content = "\n".join(lines)

        elif mutant.mutation_type == "confidence_score":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("confidence_score", "wrong_confidence")
            content = "\n".join(lines)

        elif mutant.mutation_type == "collection_equal":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("==", "!=")
            content = "\n".join(lines)

        elif mutant.mutation_type == "events_access":
            if "self._events" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace("self._events", "[]")
            content = "\n".join(lines)

        elif mutant.mutation_type == "trace_id_match":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("==", "!=")
            content = "\n".join(lines)

        elif mutant.mutation_type == "action_type_match":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("==", "!=")
            content = "\n".join(lines)

        elif mutant.mutation_type == "component_match":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("==", "!=")
            content = "\n".join(lines)

        elif mutant.mutation_type == "success_true":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("success=True", "success=False")
            content = "\n".join(lines)

        elif mutant.mutation_type == "success_false":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("success=False", "success=True")
            content = "\n".join(lines)

        elif mutant.mutation_type == "use_fallback":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("use_fallback =", "# [MUTANT] use_fallback\nuse_fallback = ")
            if "use_fallback = not" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace(
                    "use_fallback = not self.llm_api_key", 
                    "use_fallback = True"
                )
            content = "\n".join(lines)

        elif mutant.mutation_type == "total_generated":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("total_generated=", "# [MUTANT] total_generated\ntotal_generated=")
            if "total_generated=len(" in lines[mutant.line - 1]:
                lines[mutant.line - 1] = lines[mutant.line - 1].replace(
                    "total_generated=len(test_cases)", 
                    "total_generated=0"
                )
            content = "\n".join(lines)

        elif mutant.mutation_type == "fallback_used":
            lines[mutant.line - 1] = lines[mutant.line - 1].replace("fallback_used=True", "fallback_used=False")
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
        test_name = os.path.basename(test_file)
        test_dir = os.path.dirname(test_file)

        test_to_source = {
            "test_approval.py": "approval.py",
            "test_persistence.py": "approval.py",
            "test_security.py": "security.py",
            "test_tracker.py": "tracker.py",
            "test_monitoring.py": "monitoring.py",
            "test_git_manager.py": "git_manager.py",
            "test_file_lock.py": "file_lock.py",
            "test_baseline_convergence.py": "baseline.py",
            "test_concurrency.py": "process_manager.py",
            "test_convergence_loop.py": "orchestrator.py",
            "test_fixed_sdk.py": "sdk.py",
            "test_llm_config.py": "config.py",
            "test_e2e_governance.py": "orchestrator.py",
            "test_executor_transformers.py": "transformer.py",
            "test_complex_patch.py": "transformer.py",
            "test_class_match_precision.py": "transformer.py",
            "test_transformer_new.py": "transformer.py",
            "test_namespace_collision.py": "transformer.py",
            "test_mutation.py": "transformer.py",
            "test_p0_exposure.py": "transformer.py",
            "test_p0_gaps.py": "transformer.py",
            "test_effectiveness_gate.py": "transformer.py",
            "test_layered_effectiveness.py": "transformer.py",
            "test_strict_validation.py": "transformer.py",
        }

        if test_name in test_to_source:
            return os.path.join("src", "governance", test_to_source[test_name])
        elif "engine" in test_dir:
            return os.path.join("src", "engine", "pipeline.py")
        elif "ai" in test_dir:
            return os.path.join("src", "ai", "test_case_generator.py")
        elif "api_test" in test_dir:
            return os.path.join("src", "api_test", "test_runner.py")
        elif "security" in test_dir:
            return os.path.join("src", "security", "auth.py")
        elif "platform" in test_dir:
            return os.path.join("src", "platform", "api.py")
        elif "worker" in test_dir:
            return os.path.join("src", "engine", "pipeline.py")
        elif "integration" in test_dir:
            return os.path.join("src", "engine", "pipeline.py")
        elif "unit" in test_dir:
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
                message="未生成任何变异点",
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
                    [
                        "python",
                        "-m",
                        "pytest",
                        self.test_file,
                        "-v",
                        "--tb=short",
                        "--no-header",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
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
            message=message,
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
        lines.append(
            f"  {mutant.mutant_id} | {mutant.file}:{mutant.line} | {mutant.mutation_type} | {status}"
        )

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
