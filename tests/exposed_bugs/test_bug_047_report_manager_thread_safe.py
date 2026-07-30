import pytest
import threading
import os
from src.report.generator import ReportManager, generator


class TestReportManagerThreadSafe:
    def test_generate_multiple_reports_concurrently(self):
        report_manager = ReportManager()
        
        results = []
        
        def generate_report_thread(thread_id):
            try:
                context_results = {
                    f"step_{i}": {"status": "PASSED", "result": f"result_{i}"}
                    for i in range(5)
                }
                report_path = report_manager.generate(context_results)
                results.append((thread_id, report_path))
            except Exception as e:
                results.append((thread_id, f"error: {e}"))
        
        threads = [threading.Thread(target=generate_report_thread, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert all("test_report_" in r[1] for r in results), \
            f"All threads should generate reports successfully: {results}"
        assert len(set(r[1] for r in results)) == 5, "Each report should have unique filename"

    def test_module_level_generator_is_singleton(self):
        gen1 = generator
        from src.report.generator import generator as gen2
        
        assert gen1 is gen2, "Module-level generator should be singleton"