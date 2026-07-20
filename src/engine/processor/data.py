from typing import Callable, Dict

from src.core.context import ExecutionContext
from src.engine.processor.base import BaseProcessor
from src.models.contract import GrpcRequest, HttpRequest, TestStep
from src.utils.template import render_template


class DataProcessor(BaseProcessor):
    def __init__(self, strict: bool = True):
        super().__init__()
        self.strict = strict
        self._strategies = {
            "http": self._process_http,
            "grpc": self._process_grpc,
            # 未来只需在此处注册： "graphql": self._process_graphql
        }

    # 【新增】：统一获取环境上下文
    def _get_lookup_dict(self, context):
        return {**context.env, **context.vars}

    # 【新增】：通用渲染工具，处理大部分“渲染 -> 更新”的场景
    def _render_and_update(self, step, data_dict, field_name: str):
        lookup = self._get_lookup_dict(
            self.context_ref
        )  # 稍微改动下获取方式，或直接传参
        # 实际代码中可以直接通过参数传入 lookup_dict
        return render_template(
            data_dict, self._get_lookup_dict(self.context_ref), strict=self.strict
        )

    async def _run(self, context, step: TestStep, client) -> TestStep:
        # 不再赋值 self.context_ref = context
        strategy = self._strategies.get(step.protocol)
        if not strategy:
            raise ValueError(f"Unsupported protocol: {step.protocol}")

        # 将 context 直接作为参数传给策略
        return await strategy(step, context)

    async def _process_http(
        self, step: HttpRequest, context: ExecutionContext
    ) -> HttpRequest:
        lookup = self._get_lookup_dict(context)  # 直接从参数取

        # 2. 渲染 params 和 url
        new_params = render_template(step.params, lookup, strict=self.strict)
        new_url = render_template(step.url, lookup, strict=self.strict)

        # 3. 统一返回
        self.logger.debug(f"Successfully processed HTTP step: {step.step_id}")
        return step.model_copy(update={"params": new_params, "url": new_url})

    async def _process_grpc(
        self, step: GrpcRequest, context: ExecutionContext
    ) -> GrpcRequest:
        lookup = self._get_lookup_dict(context)
        new_payload = render_template(step.payload, lookup, strict=self.strict)
        return step.model_copy(update={"payload": new_payload})
