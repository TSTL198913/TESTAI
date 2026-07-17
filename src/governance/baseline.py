import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional
from src.governance.config import GovernanceConfig


class BaselineRecord:
    def __init__(self, record_id: str, baseline_type: str, data: Dict, created_at: Optional[datetime] = None):
        self.record_id = record_id
        self.baseline_type = baseline_type
        self.data = data
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> Dict:
        return {
            "record_id": self.record_id,
            "baseline_type": self.baseline_type,
            "data": self.data,
            "created_at": self.created_at.isoformat()
        }


class GoldenBaselineManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._baselines: Dict[str, BaselineRecord] = {}
        self._baseline_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../data/golden_baseline.json"
        )
        self._load_baselines()
        self._initialized = True

    def _load_baselines(self):
        if os.path.exists(self._baseline_file):
            try:
                with open(self._baseline_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for scenario in data.get("scenarios", []):
                        record_id = scenario.get("id", "")
                        baseline_type = scenario.get("type", "")
                        self._baselines[record_id] = BaselineRecord(
                            record_id=record_id,
                            baseline_type=baseline_type,
                            data=scenario
                        )
            except Exception as e:
                pass
        self._load_default_baselines()

    def _load_default_baselines(self):
        default_baselines = [
            {
                "id": "golden_sec_normal_001",
                "type": "security",
                "name": "Security Evaluator - Normal Input",
                "expected_score_min": 0.9,
                "expected_risk_level": "low",
                "expected_detected": False
            },
            {
                "id": "golden_sec_injection_001",
                "type": "security",
                "name": "Security Evaluator - Injection Attack",
                "expected_score_max": 0.4,
                "expected_risk_level": "high",
                "expected_detected": True
            },
            {
                "id": "golden_qa_high_quality_001",
                "type": "qa",
                "name": "QA Evaluator - High Quality Output",
                "expected_score_min": 0.8,
                "expected_confidence_level": ["high", "good"]
            }
        ]

        for baseline in default_baselines:
            if baseline["id"] not in self._baselines:
                self._baselines[baseline["id"]] = BaselineRecord(
                    record_id=baseline["id"],
                    baseline_type=baseline["type"],
                    data=baseline
                )

    def get_baseline(self, record_id: str) -> Optional[BaselineRecord]:
        return self._baselines.get(record_id)

    def get_baselines_by_type(self, baseline_type: str) -> List[BaselineRecord]:
        return [b for b in self._baselines.values() if b.baseline_type == baseline_type]

    def add_baseline(self, record: BaselineRecord):
        with self._lock:
            self._baselines[record.record_id] = record

    def validate_against_baseline(self, record_id: str, actual_data: Dict) -> Dict:
        baseline = self.get_baseline(record_id)
        if not baseline:
            return {"passed": False, "errors": ["Baseline not found"]}

        errors = []
        data = baseline.data
        actual_score = actual_data.get("data", {}).get("score", 0)

        if "expected_score_min" in data and actual_score < data["expected_score_min"]:
            errors.append(f"Score {actual_score} below minimum {data['expected_score_min']}")

        if "expected_score_max" in data and actual_score > data["expected_score_max"]:
            errors.append(f"Score {actual_score} exceeds maximum {data['expected_score_max']}")

        if "expected_risk_level" in data:
            actual_risk = actual_data.get("data", {}).get("data", {}).get("risk_level", "")
            if actual_risk != data["expected_risk_level"]:
                errors.append(f"Risk level {actual_risk} != expected {data['expected_risk_level']}")

        if "expected_detected" in data:
            detected = actual_data.get("data", {}).get("data", {}).get("security_tests", {}).get(
                "injection", {}).get("detected", False)
            if detected != data["expected_detected"]:
                errors.append(f"Detected {detected} != expected {data['expected_detected']}")

        if "expected_confidence_level" in data:
            confidence = actual_data.get("data", {}).get("confidence_level", "")
            if confidence not in data["expected_confidence_level"]:
                errors.append(f"Confidence level {confidence} not in {data['expected_confidence_level']}")

        return {"passed": len(errors) == 0, "errors": errors, "baseline_id": record_id}

    def calculate_convergence_score(self, actual_data: Dict, record_id: str) -> float:
        result = self.validate_against_baseline(record_id, actual_data)
        if result["passed"]:
            return 1.0
        return max(0.0, 1.0 - len(result["errors"]) * 0.2)

    def get_all_baseline_ids(self) -> List[str]:
        return list(self._baselines.keys())