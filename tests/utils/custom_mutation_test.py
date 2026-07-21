import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class MutationResult:
    file: str
    line: int
    original: str
    mutated: str
    survived: bool
    test_failed: bool
    error: str = ""


class CustomMutationTester:
    def __init__(self, target_dir: str = "src/governance/", test_files: str = "all"):
        self.target_dir = target_dir
        self.test_files = test_files
        self.results: List[MutationResult] = []
        self.mutations_applied = 0
        self.mutations_killed = 0
        self.mutations_survived = 0

    def _find_py_files(self, target_full_dir: str) -> List[str]:
        py_files = []
        if os.path.isfile(target_full_dir) and target_full_dir.endswith(".py"):
            py_files.append(target_full_dir)
        elif os.path.isdir(target_full_dir):
            for root, _, files in os.walk(target_full_dir):
                for f in files:
                    if f.endswith(".py") and not f.startswith("_"):
                        py_files.append(os.path.join(root, f))
        return py_files

    def _generate_mutations(self, file_path: str) -> List[Tuple[int, str, str]]:
        mutations = []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.strip()

            if stripped.startswith("return "):
                parts = stripped.split("return ", 1)
                if len(parts) == 2:
                    value = parts[1]
                    if value == "True":
                        mutations.append((line_num, stripped, "return False"))
                    elif value == "False":
                        mutations.append((line_num, stripped, "return True"))
                    elif value == "None":
                        mutations.append((line_num, stripped, "return \"mutated\""))
                    elif value.isdigit():
                        mutations.append((line_num, stripped, f"return {int(value) + 1}"))

            elif "==" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace("==", "!=")))

            elif "!=" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace("!=", "==")))

            elif ">" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace(">", "<")))

            elif "<" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace("<", ">")))

            elif ">=" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace(">=", "<=")))

            elif "<=" in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace("<=", ">=")))

            elif " and " in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace(" and ", " or ")))

            elif " or " in stripped and not stripped.startswith("#") and "def " not in stripped:
                mutations.append((line_num, stripped, stripped.replace(" or ", " and ")))

            elif stripped.startswith("if ") and not stripped.startswith("if __name__"):
                mutations.append((line_num, stripped, stripped.replace("if ", "if False and ")))

            elif stripped.startswith("elif ") and not stripped.startswith("elif __name__"):
                mutations.append((line_num, stripped, stripped.replace("elif ", "elif False and ")))

            elif "not " in stripped and not stripped.startswith("#"):
                mutations.append((line_num, stripped, stripped.replace("not ", "")))

            elif "raise " in stripped and not stripped.startswith("#"):
                mutations.append((line_num, stripped, "# " + stripped))

            elif stripped.startswith("except ") and not stripped.startswith("#"):
                mutations.append((line_num, stripped, stripped.replace("except ", "except NonExistentException as ")))

            elif "break" in stripped and not stripped.startswith("#"):
                mutations.append((line_num, stripped, "# " + stripped))

            elif "continue" in stripped and not stripped.startswith("#"):
                mutations.append((line_num, stripped, "# " + stripped))

        return mutations

    def _apply_mutation(self, file_path: str, line_num: int, mutated_line: str):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines[line_num - 1] = mutated_line + "\n"
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _run_tests(self, test_dir: str, test_files: str = "all", mutated_file: str = None) -> Tuple[bool, str]:
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = test_dir
            
            if test_files == "all" and mutated_file:
                pytest_args = self._build_pytest_args(mutated_file)
            elif test_files == "all":
                pytest_args = ["python", "-m", "pytest", "tests/governance/", "-q", "--tb=short", "-W", "error::RuntimeWarning"]
            elif test_files.endswith(".py"):
                pytest_args = ["python", "-m", "pytest", test_files, "-q", "--tb=short", "-W", "error::RuntimeWarning"]
            else:
                pytest_args = ["python", "-m", "pytest", "tests/governance/", "-q", "--tb=short", "-W", "error::RuntimeWarning"]
            
            result = subprocess.run(
                pytest_args,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=test_dir,
                env=env,
            )
            return result.returncode != 0, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    def _build_pytest_args(self, mutated_file: str) -> list:
        file_basename = os.path.basename(mutated_file)
        module_name = os.path.splitext(file_basename)[0]
        
        test_mapping = {
            "transformer": ["tests/governance/test_transformer_new.py"],
            "approval": ["tests/governance/test_approval.py"],
            "monitoring": ["tests/governance/test_monitoring.py"],
            "executor": ["tests/governance/test_executor_transformers.py"],
            "baseline": ["tests/governance/test_baseline_convergence.py"],
            "sdk": ["tests/governance/test_fixed_sdk.py"],
            "prompt_manager": ["tests/governance/test_llm_config.py"],
            "orchestrator": ["tests/governance/test_e2e_governance.py"],
            "git_manager": ["tests/governance/test_git_manager.py"],
            "file_lock": ["tests/governance/test_file_lock.py"],
            "agent": ["tests/governance/test_concurrency.py"],
            "tracker": ["tests/governance/test_tracker.py"],
            "process_manager": ["tests/governance/test_persistence.py"],
            "security": ["tests/governance/test_security.py"],
            "registry": ["tests/governance/test_namespace_collision.py"],
            "resilience": ["tests/governance/test_p0_exposure.py"],
            "models": ["tests/governance/test_class_match_precision.py"],
            "config": ["tests/governance/test_llm_config.py"],
        }
        
        if module_name in test_mapping:
            return ["python", "-m", "pytest"] + test_mapping[module_name] + ["-q", "--tb=short"]
        
        return ["python", "-m", "pytest", "tests/governance/", "-q", "--tb=short"]

    def run(self) -> dict:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        target_full_dir = os.path.join(project_root, self.target_dir)

        py_files = self._find_py_files(target_full_dir)
        print(f"Project root: {project_root}")
        print(f"Target directory: {target_full_dir}")
        print(f"Found {len(py_files)} Python files to mutate")

        if not py_files:
            return self._generate_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"\nUsing temporary directory: {temp_dir}")

            src_dest = os.path.join(temp_dir, "src")
            tests_dest = os.path.join(temp_dir, "tests")

            shutil.copytree(os.path.join(project_root, "src"), src_dest)
            shutil.copytree(os.path.join(project_root, "tests"), tests_dest)

            for file_path in py_files:
                rel_path = os.path.relpath(file_path, project_root)
                temp_file_path = os.path.join(temp_dir, rel_path)
                print(f"\nProcessing: {rel_path}")
                mutations = self._generate_mutations(temp_file_path)
                print(f"  Generated {len(mutations)} mutations")

                for line_num, original, mutated in mutations:
                    self.mutations_applied += 1

                    try:
                        backup_path = temp_file_path + ".mut_bak"
                        shutil.copy2(temp_file_path, backup_path)

                        self._apply_mutation(temp_file_path, line_num, mutated)

                        test_failed, error = self._run_tests(temp_dir, self.test_files, mutated_file=rel_path)

                        survived = not test_failed
                        if survived:
                            self.mutations_survived += 1
                            print(f"  ❌ SURVIVED: Line {line_num}")
                        else:
                            self.mutations_killed += 1
                            print(f"  ✅ KILLED: Line {line_num}")

                        self.results.append(
                            MutationResult(
                                file=rel_path,
                                line=line_num,
                                original=original,
                                mutated=mutated,
                                survived=survived,
                                test_failed=test_failed,
                                error=error,
                            )
                        )

                        shutil.copy2(backup_path, temp_file_path)
                        if os.path.exists(backup_path):
                            os.remove(backup_path)

                    except Exception as e:
                        self.results.append(
                            MutationResult(
                                file=rel_path,
                                line=line_num,
                                original=original,
                                mutated=mutated,
                                survived=True,
                                test_failed=False,
                                error=str(e),
                            )
                        )
                        self.mutations_survived += 1
                        print(f"  ⚠️ ERROR: Line {line_num} - {e}")
                        if os.path.exists(temp_file_path + ".mut_bak"):
                            shutil.copy2(temp_file_path + ".mut_bak", temp_file_path)
                            os.remove(temp_file_path + ".mut_bak")

        return self._generate_report()

    def _generate_report(self) -> dict:
        kill_rate = (
            (self.mutations_killed / self.mutations_applied * 100)
            if self.mutations_applied > 0
            else 0
        )

        report = {
            "summary": {
                "mutations_applied": self.mutations_applied,
                "mutations_killed": self.mutations_killed,
                "mutations_survived": self.mutations_survived,
                "kill_rate": f"{kill_rate:.2f}%",
                "kill_rate_numeric": kill_rate,
            },
            "results": [],
            "survived_mutations": [],
        }

        for result in self.results:
            result_dict = {
                "file": result.file,
                "line": result.line,
                "original": result.original.strip(),
                "mutated": result.mutated.strip(),
                "survived": result.survived,
                "error": result.error,
            }
            report["results"].append(result_dict)
            if result.survived:
                report["survived_mutations"].append(result_dict)

        return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Custom Mutation Testing Tool")
    parser.add_argument("--target", type=str, default="src/governance/", help="Target directory to mutate")
    parser.add_argument("--test", type=str, default="all", help="Test file to run")
    args = parser.parse_args()
    
    print(f"Starting mutation testing...")
    print(f"Target directory: {args.target}")
    print(f"Test file: {args.test}")
    
    tester = CustomMutationTester(target_dir=args.target, test_files=args.test)
    report = tester.run()

    print("\n" + "=" * 60)
    print("MUTATION TESTING REPORT")
    print("=" * 60)
    print(f"Mutations applied: {report['summary']['mutations_applied']}")
    print(f"Mutations killed: {report['summary']['mutations_killed']}")
    print(f"Mutations survived: {report['summary']['mutations_survived']}")
    print(f"Kill rate: {report['summary']['kill_rate']}")

    if report["survived_mutations"]:
        print("\nSurvived mutations (test improvement opportunities):")
        for mut in report["survived_mutations"]:
            print(f"\n  File: {mut['file']}:{mut['line']}")
            print(f"  Original: {mut['original']}")
            print(f"  Mutated: {mut['mutated']}")
            if mut["error"]:
                print(f"  Error: {mut['error']}")

    with open("mutation_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to mutation_results.json")
    return report


if __name__ == "__main__":
    main()