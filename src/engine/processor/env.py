# src/engine/processor/env.py
from src.engine.processor.base import BaseProcessor

class EnvironmentProcessor(BaseProcessor):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    async def process(self, context, step, client):
        context.env.update(self.config)
        self.logger.info(f"Environment loaded: {self.config}")
        return step