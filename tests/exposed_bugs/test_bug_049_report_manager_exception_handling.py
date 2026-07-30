import pytest
from unittest.mock import patch, MagicMock
from src.report.generator import ReportManager


class TestReportManagerExceptionHandling:
    def test_generate_handles_template_rendering_error(self):
        report_manager = ReportManager()
        
        context_results = {"step_1": {"status": "PASSED", "result": "test"}}
        
        with patch.object(report_manager.env, 'get_template', side_effect=Exception("Template not found")):
            report_path = report_manager.generate(context_results)
            
            assert report_path is None

    def test_generate_handles_file_write_error(self):
        report_manager = ReportManager()
        
        context_results = {"step_1": {"status": "PASSED", "result": "test"}}
        
        with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
            report_path = report_manager.generate(context_results)
            
            assert report_path is None