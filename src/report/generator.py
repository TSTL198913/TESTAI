# src/report/generator.py
import datetime
import uuid
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


class ReportManager:
    def __init__(self, template_dir="src/report/templates"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "htm", "xml"]),
        )
        self.report_dir = Path("reports")
        self.report_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def generate(self, context_results: dict):
        try:
            total = len(context_results)
            passed = sum(
                1 for res in context_results.values() if res.get("status") == "PASSED"
            )

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            output_file = self.report_dir / f"test_report_{timestamp}_{unique_id}.html"

            template = self.env.get_template("report_template.html")
            html_content = template.render(
                results=context_results,
                stats={
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%",
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

            output_file.write_text(html_content, encoding="utf-8")
            return str(output_file)
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            return None


generator = ReportManager()
