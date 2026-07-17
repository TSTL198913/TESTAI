# src/engine/factory.py
from pydantic import TypeAdapter, ValidationError

from src.engine.transformers import TRANSFORMER_REGISTRY
from src.models.contract import TestStep

step_adapter = TypeAdapter(TestStep)


class FactoryError(Exception): pass


class StepFactory:
    @staticmethod
    def create(raw_step: dict) -> TestStep:
        try:
            protocol = raw_step.get("protocol", "http")

            # 1. 如果有嵌套结构（如 'http' 键），优先提取内部数据
            # 假设 transformer 返回的是 {'protocol': 'http', 'http': {...}}
            if protocol in raw_step and isinstance(raw_step[protocol], dict):
                data_to_validate = raw_step[protocol]
            else:
                data_to_validate = raw_step

            # 2. 注入协议字段，满足 Pydantic 校验需求
            data_to_validate["protocol"] = protocol

            # 3. 校验
            return step_adapter.validate_python(data_to_validate)

        except ValidationError as e:
            raise FactoryError(f"步骤 {raw_step.get('step_id')} 契约校验失败: {e.errors()}")