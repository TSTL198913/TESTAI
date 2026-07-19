# src/engine/pipeline.py
import logging
from typing import List

import httpx

from src.engine.factory import StepFactory
from src.engine.processor.base import BaseProcessor

logger = logging.getLogger(__name__)


class ExecutionPipeline:
    def __init__(self, processors: List[BaseProcessor]):
        self.processors = processors

    async def run(self, context, raw_steps: List[dict], client: httpx.AsyncClient):
        processed_steps = []
        all_exceptions = []

        for raw_step in raw_steps:
            step = StepFactory.create(raw_step)
            context.results[step.step_id] = {"status": "RUNNING"}

            is_failed = False
            last_exception = None

            for processor in self.processors:
                is_governance_processor = isinstance(processor, BaseProcessor) and hasattr(processor, 'engine') and \
                                         processor.__class__.__name__ == "GovernanceProcessor"

                if is_failed and not is_governance_processor:
                    continue

                try:
                    step = await processor.process(context, step, client)
                except Exception as e:
                    logger.error(f"[Pipeline] Step {step.step_id} failed in {processor.__class__.__name__}: {str(e)}")
                    result = context.results.get(step.step_id, {})
                    result["status"] = "FAILED"
                    result["error"] = e
                    context.results[step.step_id] = result
                    is_failed = True
                    last_exception = e

            if not is_failed:
                context.results[step.step_id]["status"] = "PASSED"

            processed_steps.append(step)

            if is_failed and last_exception:
                all_exceptions.append(last_exception)

        if all_exceptions:
            raise all_exceptions[0]

        return processed_steps