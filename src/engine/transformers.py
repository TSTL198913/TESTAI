# src/engine/transformers.py
from typing import Any, Dict


class StepTransformer:
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class HttpTransformer(StepTransformer):
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        result = raw_step.copy()
        params = result.get("params", {})

        result["url"] = params.get("url")
        result["method"] = params.get("method", "GET")
        result.pop("params", None)

        return result


class GrpcTransformer(StepTransformer):
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        return raw_step.copy()


TRANSFORMER_REGISTRY = {"http": HttpTransformer(), "grpc": GrpcTransformer()}
