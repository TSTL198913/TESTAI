import json
import os
from typing import Any, Dict, List, Optional, Tuple


class ValidationError(Exception):
    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.path = path


class ValidationResult:
    def __init__(self):
        self.passed: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.matched_fields: int = 0
        self.total_fields: int = 0

    def add_error(self, message: str):
        self.passed = False
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)


class EvaluationValidator:
    def __init__(self, baseline_path: str = None):
        if baseline_path is None:
            baseline_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "golden_baseline.json",
            )
        self.baseline_path = baseline_path
        self.baseline_data: Dict[str, Any] = {}
        self.load_baseline()

    def load_baseline(self) -> None:
        if not os.path.exists(self.baseline_path):
            raise FileNotFoundError(f"Golden baseline not found: {self.baseline_path}")

        with open(self.baseline_path, "r", encoding="utf-8") as f:
            self.baseline_data = json.load(f)

    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        for scenario in self.baseline_data.get("scenarios", []):
            if scenario["id"] == scenario_id:
                return scenario
        return None

    def get_scenarios_by_type(self, evaluator_type: str) -> List[Dict[str, Any]]:
        return [
            scenario
            for scenario in self.baseline_data.get("scenarios", [])
            if scenario.get("evaluator_type") == evaluator_type
        ]

    def validate(
        self, actual_output: Dict[str, Any], scenario_id: str
    ) -> ValidationResult:
        scenario = self.get_scenario(scenario_id)
        if scenario is None:
            result = ValidationResult()
            result.add_error(f"Scenario not found: {scenario_id}")
            return result

        expected_output = scenario["expected_output"]
        return self._validate_recursive(actual_output, expected_output, "")

    def _validate_recursive(
        self, actual: Any, expected: Any, current_path: str
    ) -> ValidationResult:
        result = ValidationResult()
        result.total_fields += 1

        if expected is None:
            result.matched_fields += 1
            return result

        if isinstance(expected, dict):
            if "type" in expected:
                return self._validate_type_constraint(actual, expected, current_path)
            if "oneOf" in expected:
                return self._validate_one_of(actual, expected, current_path)
            if "min" in expected and "max" in expected:
                return self._validate_range(actual, expected, current_path)
            if expected == {}:
                if isinstance(actual, dict):
                    result.matched_fields += 1
                    return result
                else:
                    result.add_error(
                        f"Expected object at {current_path}, got {type(actual).__name__}"
                    )
                    return result

            if not isinstance(actual, dict):
                result.add_error(
                    f"Expected dict at {current_path}, got {type(actual).__name__}"
                )
                return result

            for key, expected_value in expected.items():
                actual_value = actual.get(key)
                key_path = f"{current_path}.{key}" if current_path else key
                sub_result = self._validate_recursive(
                    actual_value, expected_value, key_path
                )
                result.passed &= sub_result.passed
                result.errors.extend(sub_result.errors)
                result.warnings.extend(sub_result.warnings)
                result.matched_fields += sub_result.matched_fields
                result.total_fields += sub_result.total_fields - 1

        elif isinstance(expected, list):
            if not isinstance(actual, list):
                result.add_error(
                    f"Expected list at {current_path}, got {type(actual).__name__}"
                )
                return result
            result.matched_fields += 1

        else:
            if actual == expected:
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Mismatch at {current_path}: expected {expected!r}, got {actual!r}"
                )

        return result

    def _validate_type_constraint(
        self, actual: Any, expected: Dict[str, Any], path: str
    ) -> ValidationResult:
        result = ValidationResult()
        type_name = expected["type"]

        if type_name == "string":
            if isinstance(actual, str):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected string at {path}, got {type(actual).__name__}"
                )
        elif type_name == "number":
            if isinstance(actual, (int, float)):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected number at {path}, got {type(actual).__name__}"
                )
        elif type_name == "integer":
            if isinstance(actual, int):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected integer at {path}, got {type(actual).__name__}"
                )
        elif type_name == "boolean":
            if isinstance(actual, bool):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected boolean at {path}, got {type(actual).__name__}"
                )
        elif type_name == "array":
            if isinstance(actual, list):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected array at {path}, got {type(actual).__name__}"
                )
        elif type_name == "object":
            if isinstance(actual, dict):
                result.matched_fields += 1
            else:
                result.add_error(
                    f"Expected object at {path}, got {type(actual).__name__}"
                )
        elif type_name == "null":
            if actual is None:
                result.matched_fields += 1
            else:
                result.add_error(f"Expected null at {path}, got {actual!r}")
        else:
            result.add_error(f"Unknown type constraint {type_name!r} at {path}")

        return result

    def _validate_one_of(
        self, actual: Any, expected: Dict[str, Any], path: str
    ) -> ValidationResult:
        result = ValidationResult()
        options = expected["oneOf"]

        if actual in options:
            result.matched_fields += 1
        else:
            result.add_error(f"Expected one of {options} at {path}, got {actual!r}")

        return result

    def _validate_range(
        self, actual: Any, expected: Dict[str, Any], path: str
    ) -> ValidationResult:
        result = ValidationResult()
        min_val = expected["min"]
        max_val = expected["max"]

        if not isinstance(actual, (int, float)):
            result.add_error(
                f"Expected numeric value at {path}, got {type(actual).__name__}"
            )
            return result

        if min_val is not None and actual < min_val:
            result.add_error(f"Value {actual} at {path} is below minimum {min_val}")
        elif max_val is not None and actual > max_val:
            result.add_error(f"Value {actual} at {path} exceeds maximum {max_val}")
        else:
            result.matched_fields += 1

        return result

    def calculate_convergence_score(self, validation_result: ValidationResult) -> float:
        if validation_result.total_fields == 0:
            return 0.0
        return validation_result.matched_fields / validation_result.total_fields
