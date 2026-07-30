import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.pipeline import ExecutionPipeline


class TestPipelineGovernanceDetection:
    def test_governance_processor_identified_by_class_name(self):
        """边界：治理处理器应通过类名正确识别"""
        class GovernanceProcessor:
            pass
        
        class OtherProcessor:
            pass
        
        governance_processor = GovernanceProcessor()
        other_processor = OtherProcessor()
        
        assert governance_processor.__class__.__name__ == "GovernanceProcessor"
        assert other_processor.__class__.__name__ != "GovernanceProcessor"

    @pytest.mark.asyncio
    async def test_failed_step_stops_non_governance_processors(self):
        """正向：失败步骤应跳过非治理处理器"""
        context = MagicMock()
        context.results = {}
        
        governance_processor = AsyncMock()
        governance_processor.__class__.__name__ = "GovernanceProcessor"
        governance_processor.process.return_value = MagicMock()
        
        other_processor = AsyncMock()
        other_processor.__class__.__name__ = "OtherProcessor"
        other_processor.process.side_effect = Exception("Test failure")
        
        pipeline = ExecutionPipeline([other_processor, governance_processor])
        
        step = MagicMock()
        step.step_id = "test_step"
        
        raw_steps = [{"step_id": "test_step", "protocol": "http", "method": "GET", "url": "http://test.com", "description": "Test step"}]
        client = AsyncMock()
        
        with pytest.raises(Exception):
            await pipeline.run(context, raw_steps, client)
        
        other_processor.process.assert_called_once()
        governance_processor.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_step_skips_non_governance_processors(self):
        """正向：失败步骤应跳过后续非治理处理器"""
        context = MagicMock()
        context.results = {}
        
        processor1 = AsyncMock()
        processor1.__class__.__name__ = "Processor1"
        processor1.process.side_effect = Exception("Test failure")
        
        processor2 = AsyncMock()
        processor2.__class__.__name__ = "Processor2"
        
        governance_processor = AsyncMock()
        governance_processor.__class__.__name__ = "GovernanceProcessor"
        governance_processor.process.return_value = MagicMock()
        
        pipeline = ExecutionPipeline([processor1, processor2, governance_processor])
        
        raw_steps = [{"step_id": "test_step", "protocol": "http", "method": "GET", "url": "http://test.com", "description": "Test step"}]
        client = AsyncMock()
        
        with pytest.raises(Exception):
            await pipeline.run(context, raw_steps, client)
        
        processor1.process.assert_called_once()
        processor2.process.assert_not_called()
        governance_processor.process.assert_called_once()