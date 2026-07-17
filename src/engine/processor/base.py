# src/engine/processor/base.py
import logging
from abc import ABC
from src.core.exceptions import ProcessorError


class BaseProcessor(ABC):
    # 使用 property 方式，这样即使没初始化 __init__，也不会抛出 AttributeError
    @property
    def logger(self):
        if not hasattr(self, "_logger"):
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger

    async def process(self, context, step, client):
        try:
            return await self._run(context, step, client)
        except Exception as e:
            # 不要传 ...，传具体的异常信息
            error_msg = f"Processor {self.__class__.__name__} failed: {str(e)}"
            self.logger.error(error_msg)
            raise ProcessorError(error_msg) from e