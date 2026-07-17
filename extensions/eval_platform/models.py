# extensions/eval_platform/models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Any


class EvaluationRequest(BaseModel):
    id: str
    task_type: str = "evaluation"
    model_provider: str
    payload: dict


class DomainResponse(BaseModel):
    score: float
    evaluation_status: str
    confidence: float
    data: Optional[Any] = None


class EvalRequestContract(BaseModel):
    protocol: str = "eval_platform"
    endpoint: str = "/api/v1/evaluate"
    method: str = "POST"
    request_body: EvaluationRequest