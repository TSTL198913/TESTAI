import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
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
    def __init__(
        self,
        target_dir: str = "src/governance/",
        test_command: str = "python -m pytest -x -q",
    ):
        self.target_dir = target_dir
        self.test_command = test_command
        self.results: List[MutationResult] = []
        self.mutations_applied = 0
        self.mutations_killed = 0
        self.mutations_survived = 0

    def _find_py_files(self) -> List[str]:
        py_files = []
        for root, _, files in os.walk(self.target_dir):
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
                        mutations.append((line_num, stripped, 'return "mutated"'))
                    elif value == '""':
                        mutations.append((line_num, stripped, 'return "mutated"'))

            elif (
                "==" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("==", "!=")))

            elif (
                "!=" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("!=", "==")))

            elif (
                "<" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and "<=" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("<", ">")))

            elif (
                ">" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and ">=" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace(">", "<")))

            elif (
                "<=" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("<=", ">=")))

            elif (
                ">=" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace(">=", "<=")))

            elif (
                " and " in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append(
                    (line_num, stripped, stripped.replace(" and ", " or "))
                )

            elif (
                " or " in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
            ):
                mutations.append(
                    (line_num, stripped, stripped.replace(" or ", " and "))
                )

            elif stripped.startswith("if "):
                mutations.append(
                    (line_num, stripped, stripped.replace("if ", "if False and "))
                )

            elif stripped.startswith("elif "):
                mutations.append(
                    (line_num, stripped, stripped.replace("elif ", "elif False and "))
                )

            elif stripped.startswith("while "):
                mutations.append(
                    (line_num, stripped, stripped.replace("while ", "while False and "))
                )

            elif (
                "+" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and "=" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("+", "-")))

            elif (
                "-" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and "=" not in stripped
                and "return" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("-", "+")))

            elif (
                "*" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and "=" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("*", "/")))

            elif (
                "/" in stripped
                and not stripped.startswith("#")
                and "def " not in stripped
                and "=" not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("/", "*")))

            elif (
                '"' in stripped
                and not stripped.startswith("#")
                and "return" in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace('"', "'")))

            elif (
                "'" in stripped
                and not stripped.startswith("#")
                and "return" in stripped
                and '"' not in stripped
            ):
                mutations.append((line_num, stripped, stripped.replace("'", '"')))

            elif "not " in stripped and not stripped.startswith("#"):
                mutations.append((line_num, stripped, stripped.replace("not ", "")))

        return mutations

    def _apply_mutation(self, file_path: str, line_num: int, mutated_line: str):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        lines[line_num - 1] = mutated_line + "\n"

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _run_tests(self, test_dir: str) -> Tuple[bool, str]:
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = test_dir

            result = subprocess.run(
                self.test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=test_dir,
                env=env,
            )
            return result.returncode != 0, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    def run(self) -> dict:
        py_files = self._find_py_files()
        print(f"Found {len(py_files)} Python files to mutate")

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            temp_project = os.path.join(temp_dir, "test_project")
            shutil.copytree(project_root, temp_project, dirs_exist_ok=True)

            for file_path in py_files:
                rel_path = os.path.relpath(file_path, project_root)
                temp_file_path = os.path.join(temp_project, rel_path)

                print(f"\nProcessing: {rel_path}")
                mutations = self._generate_mutations(file_path)
                print(f"  Generated {len(mutations)} mutations")

                for line_num, original, mutated in mutations:
                    self.mutations_applied += 1

                    try:
                        shutil.copy2(file_path, temp_file_path)

                        self._apply_mutation(temp_file_path, line_num, mutated)

                        test_failed, error = self._run_tests(temp_project)

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
    import json

    tester = CustomMutationTester(
        target_dir="src/governance/",
        test_command="python -m pytest tests/governance/ -x -q --tb=short",
    )

    report = tester.run()

    output = []
    output.append("\n" + "=" * 60)
    output.append("MUTATION TESTING REPORT")
    output.append("=" * 60)
    output.append(f"Mutations applied: {report['summary']['mutations_applied']}")
    output.append(f"Mutations killed: {report['summary']['mutations_killed']}")
    output.append(f"Mutations survived: {report['summary']['mutations_survived']}")
    output.append(f"Kill rate: {report['summary']['kill_rate']}")

    if report["survived_mutations"]:
        output.append("\nSurvived mutations (test improvement opportunities):")
        for mut in report["survived_mutations"]:
            output.append(f"\n  File: {mut['file']}:{mut['line']}")
            output.append(f"  Original: {mut['original']}")
            output.append(f"  Mutated: {mut['mutated']}")
            if mut["error"]:
                output.append(f"  Error: {mut['error']}")

    print("\n".join(output))

    with open("mutation_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to mutation_results.json")

    return report


if __name__ == "__main__":
    main()
