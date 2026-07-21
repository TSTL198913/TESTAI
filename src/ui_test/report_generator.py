import os
import json
from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


@dataclass
class TestResult:
    test_id: str
    test_name: str
    status: str
    duration_ms: int
    error_message: str = ""
    screenshot_path: str = ""
    logs: List[str] = field(default_factory=list)


@dataclass
class ReportSummary:
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int = 0
    duration_ms: int = 0
    pass_rate: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)


class HtmlReportGenerator:
    def __init__(self, report_dir: str = "reports"):
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)

    def generate(self, summary: ReportSummary, results: List[TestResult]) -> str:
        env = Environment(
            loader=FileSystemLoader(os.path.dirname(__file__)),
            autoescape=True,
        )

        template = env.from_string(self._get_template())

        data = {
            "summary": {
                "total_tests": summary.total_tests,
                "passed_tests": summary.passed_tests,
                "failed_tests": summary.failed_tests,
                "skipped_tests": summary.skipped_tests,
                "duration_ms": summary.duration_ms,
                "duration_formatted": self._format_duration(summary.duration_ms),
                "pass_rate": f"{summary.pass_rate:.2f}%",
                "start_time": summary.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": summary.end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": self._get_overall_status(summary),
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "test_name": r.test_name,
                    "status": r.status,
                    "status_class": self._get_status_class(r.status),
                    "status_icon": self._get_status_icon(r.status),
                    "duration_ms": r.duration_ms,
                    "duration_formatted": self._format_duration(r.duration_ms),
                    "error_message": r.error_message,
                    "screenshot_path": r.screenshot_path.replace("\\", "/"),
                    "has_screenshot": bool(r.screenshot_path),
                    "logs": r.logs,
                }
                for r in results
            ],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        html = template.render(data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.report_dir, f"test_report_{timestamp}.html")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        return report_path

    def _get_template(self) -> str:
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TestAI UI自动化测试报告</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; }
        
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; }
        .header h1 { font-size: 24px; font-weight: 600; }
        .header .meta { font-size: 14px; opacity: 0.8; margin-top: 8px; }
        
        .container { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
        
        .summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .card .value { font-size: 32px; font-weight: 700; margin-bottom: 4px; }
        .card .label { font-size: 14px; color: #666; }
        .card.success { border-top: 4px solid #10b981; }
        .card.success .value { color: #10b981; }
        .card.failure { border-top: 4px solid #ef4444; }
        .card.failure .value { color: #ef4444; }
        .card.warning { border-top: 4px solid #f59e0b; }
        .card.warning .value { color: #f59e0b; }
        .card.info { border-top: 4px solid #3b82f6; }
        .card.info .value { color: #3b82f6; }
        
        .status-badge { display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }
        .status-badge.passed { background: #d1fae5; color: #065f46; }
        .status-badge.failed { background: #fee2e2; color: #991b1b; }
        .status-badge.skipped { background: #f3f4f6; color: #6b7280; }
        
        .test-list { background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }
        .test-item { border-bottom: 1px solid #f0f0f0; padding: 16px; }
        .test-item:last-child { border-bottom: none; }
        .test-item:hover { background: #fafafa; }
        
        .test-header { display: flex; justify-content: space-between; align-items: center; }
        .test-name { font-size: 16px; font-weight: 600; }
        .test-meta { display: flex; gap: 16px; font-size: 14px; color: #666; }
        
        .details { margin-top: 12px; padding: 12px; background: #f8fafc; border-radius: 8px; display: none; }
        .details.show { display: block; }
        
        .error { color: #dc2626; font-family: monospace; font-size: 13px; white-space: pre-wrap; }
        .logs { margin-top: 8px; font-family: monospace; font-size: 12px; color: #475569; max-height: 150px; overflow-y: auto; }
        
        .screenshot { margin-top: 8px; border-radius: 8px; overflow: hidden; max-width: 600px; }
        .screenshot img { width: 100%; display: block; }
        
        .btn { background: #667eea; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .btn:hover { background: #5a6fd6; }
        
        .footer { text-align: center; padding: 24px; color: #9ca3af; font-size: 13px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>TestAI UI自动化测试报告</h1>
        <div class="meta">
            生成时间: {{ generated_at }} | 
            执行时间: {{ summary.start_time }} - {{ summary.end_time }}
        </div>
    </div>
    
    <div class="container">
        <div class="summary-cards">
            <div class="card info">
                <div class="value">{{ summary.total_tests }}</div>
                <div class="label">总测试用例</div>
            </div>
            <div class="card success">
                <div class="value">{{ summary.passed_tests }}</div>
                <div class="label">通过</div>
            </div>
            <div class="card failure">
                <div class="value">{{ summary.failed_tests }}</div>
                <div class="label">失败</div>
            </div>
            <div class="card warning">
                <div class="value">{{ summary.pass_rate }}</div>
                <div class="label">通过率</div>
            </div>
            <div class="card info">
                <div class="value">{{ summary.duration_formatted }}</div>
                <div class="label">总耗时</div>
            </div>
        </div>
        
        <div class="test-list">
            {% for result in results %}
            <div class="test-item">
                <div class="test-header">
                    <div>
                        <span class="test-name">{{ result.test_name }}</span>
                        <span class="status-badge {{ result.status_class }}">
                            {{ result.status_icon }} {{ result.status }}
                        </span>
                    </div>
                    <div class="test-meta">
                        <span>ID: {{ result.test_id }}</span>
                        <span>耗时: {{ result.duration_formatted }}</span>
                        {% if result.has_screenshot %}
                        <button class="btn" onclick="toggleDetails('{{ result.test_id }}')">查看详情</button>
                        {% endif %}
                    </div>
                </div>
                <div id="details-{{ result.test_id }}" class="details">
                    {% if result.error_message %}
                    <div class="error">错误信息: {{ result.error_message }}</div>
                    {% endif %}
                    {% if result.has_screenshot %}
                    <div class="screenshot">
                        <img src="{{ result.screenshot_path }}" alt="截图">
                    </div>
                    {% endif %}
                    {% if result.logs %}
                    <div class="logs">
                        <strong>执行日志:</strong><br>
                        {% for log in result.logs %}
                        {{ log }}<br>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="footer">
        Generated by TestAI Playwright Runner
    </div>
    
    <script>
        function toggleDetails(id) {
            const el = document.getElementById('details-' + id);
            el.classList.toggle('show');
        }
    </script>
</body>
</html>
"""

    def _format_duration(self, ms: int) -> str:
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{(ms / 1000):.1f}s"
        else:
            minutes = int(ms / 60000)
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"

    def _get_overall_status(self, summary: ReportSummary) -> str:
        if summary.failed_tests == 0:
            return "全部通过"
        elif summary.failed_tests <= summary.total_tests * 0.1:
            return "部分失败"
        else:
            return "严重失败"

    def _get_status_class(self, status: str) -> str:
        if status == "passed":
            return "passed"
        elif status == "failed":
            return "failed"
        else:
            return "skipped"

    def _get_status_icon(self, status: str) -> str:
        if status == "passed":
            return "✓"
        elif status == "failed":
            return "✗"
        else:
            return "○"


class JsonReportGenerator:
    def __init__(self, report_dir: str = "reports"):
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)

    def generate(self, summary: ReportSummary, results: List[TestResult]) -> str:
        data = {
            "summary": {
                "total_tests": summary.total_tests,
                "passed_tests": summary.passed_tests,
                "failed_tests": summary.failed_tests,
                "skipped_tests": summary.skipped_tests,
                "duration_ms": summary.duration_ms,
                "pass_rate": summary.pass_rate,
                "start_time": summary.start_time.isoformat(),
                "end_time": summary.end_time.isoformat(),
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "test_name": r.test_name,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "error_message": r.error_message,
                    "screenshot_path": r.screenshot_path,
                    "logs": r.logs,
                }
                for r in results
            ],
            "generated_at": datetime.now().isoformat(),
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.report_dir, f"test_report_{timestamp}.json")

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return report_path