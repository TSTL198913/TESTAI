# src/engine/transformers.py
from typing import Dict, Any


class StepTransformer:
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class HttpTransformer(StepTransformer):
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        params = raw_step.get("params", {})

        # 【修改点】：直接将字段平铺到 raw_step 根节点
        raw_step["url"] = params.get("url")
        raw_step["method"] = params.get("method", "GET")

        # 移除 params，保持数据整洁 (可选)
        raw_step.pop("params", None)

        return raw_step


class GrpcTransformer(StepTransformer):
    def transform(self, raw_step: Dict[str, Any]) -> Dict[str, Any]:
        return raw_step


TRANSFORMER_REGISTRY = {
    "http": HttpTransformer(),
    "grpc": GrpcTransformer()
}