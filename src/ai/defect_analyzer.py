import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class DefectSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DefectType(str, Enum):
    LOGIC_ERROR = "logic_error"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    USABILITY = "usability"
    DATA_INTEGRITY = "data_integrity"


@dataclass
class DefectFinding:
    id: str
    title: str
    severity: DefectSeverity
    defect_type: DefectType
    description: str
    location: str = ""
    code_snippet: str = ""
    suggested_fix: str = ""
    confidence: float = 0.0
    related_tests: List[str] = field(default_factory=list)
    found_at: datetime = field(default_factory=datetime.now)


@dataclass
class AnalysisResult:
    success: bool
    findings: List[DefectFinding] = field(default_factory=list)
    error_message: str = ""
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    fallback_used: bool = False


class DefectAnalyzer:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key

    def analyze_test_results(self, test_results: Dict[str, Any]) -> AnalysisResult:
        if self.use_fallback:
            return self._analyze_fallback(test_results)
        
        try:
            return self._analyze_with_llm(test_results)
        except Exception as e:
            return AnalysisResult(
                success=False,
                error_message=f"LLM analysis failed: {str(e)}",
                fallback_used=True,
                findings=self._analyze_fallback(test_results).findings,
            )

    def analyze_code(self, code: str, file_path: str = "") -> AnalysisResult:
        if self.use_fallback:
            return self._analyze_code_fallback(code, file_path)
        
        try:
            return self._analyze_code_with_llm(code, file_path)
        except Exception as e:
            return AnalysisResult(
                success=False,
                error_message=f"LLM analysis failed: {str(e)}",
                fallback_used=True,
                findings=self._analyze_code_fallback(code, file_path).findings,
            )

    def _analyze_with_llm(self, test_results: Dict[str, Any]) -> AnalysisResult:
        prompt = self._build_test_analysis_prompt(test_results)
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "你是一个专业的缺陷分析专家，能够分析测试结果并识别潜在的缺陷和问题。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")
            result = json.loads(content)
            return self._parse_llm_analysis(result)
            
        except Exception as e:
            raise e

    def _analyze_fallback(self, test_results: Dict[str, Any]) -> AnalysisResult:
        findings = []
        failures = test_results.get("failures", [])
        errors = test_results.get("errors", [])
        
        for idx, failure in enumerate(failures):
            findings.append(DefectFinding(
                id=f"defect_{idx}",
                title=f"测试失败: {failure.get('test_name', 'unknown')}",
                severity=self._infer_severity(failure),
                defect_type=self._infer_defect_type(failure),
                description=failure.get("error_message", "测试失败"),
                location=failure.get("location", ""),
                code_snippet=failure.get("code_snippet", ""),
                confidence=0.7,
                related_tests=[failure.get("test_name", "")],
            ))
        
        for idx, error in enumerate(errors):
            findings.append(DefectFinding(
                id=f"error_{idx}",
                title=f"执行错误: {error.get('test_name', 'unknown')}",
                severity=DefectSeverity.HIGH,
                defect_type=DefectType.LOGIC_ERROR,
                description=error.get("error_message", "执行错误"),
                location=error.get("location", ""),
                confidence=0.6,
                related_tests=[error.get("test_name", "")],
            ))
        
        return self._build_analysis_result(findings)

    def _analyze_code_fallback(self, code: str, file_path: str) -> AnalysisResult:
        findings = []
        
        if re.search(r"password\s*=\s*['\"][^'\"]*['\"]", code):
            findings.append(DefectFinding(
                id="security_hardcoded_password",
                title="硬编码密码",
                severity=DefectSeverity.CRITICAL,
                defect_type=DefectType.SECURITY,
                description="代码中发现硬编码的密码，存在安全风险",
                location=file_path,
                suggested_fix="将密码移至环境变量或配置文件",
                confidence=0.95,
            ))
        
        if re.search(r"except\s*:\s*pass", code):
            findings.append(DefectFinding(
                id="silent_exception",
                title="静默异常处理",
                severity=DefectSeverity.MEDIUM,
                defect_type=DefectType.LOGIC_ERROR,
                description="发现空的except块，可能隐藏潜在问题",
                location=file_path,
                suggested_fix="添加适当的异常处理和日志记录",
                confidence=0.8,
            ))
        
        if re.search(r"print\s*\(", code) and "def " in code:
            findings.append(DefectFinding(
                id="print_debug",
                title="调试打印语句",
                severity=DefectSeverity.LOW,
                defect_type=DefectType.USABILITY,
                description="生产代码中发现调试用的print语句",
                location=file_path,
                suggested_fix="替换为日志记录",
                confidence=0.7,
            ))
        
        if re.search(r"==\s*None", code):
            findings.append(DefectFinding(
                id="equality_none",
                title="None值比较使用==",
                severity=DefectSeverity.LOW,
                defect_type=DefectType.LOGIC_ERROR,
                description="应使用is None而非== None",
                location=file_path,
                suggested_fix="替换为is None",
                confidence=0.85,
            ))
        
        return self._build_analysis_result(findings)

    def _build_test_analysis_prompt(self, test_results: Dict[str, Any]) -> str:
        return f"""
分析以下测试结果，识别潜在缺陷：

测试摘要：{json.dumps(test_results.get('summary', {}), indent=2, ensure_ascii=False)}

失败的测试：{json.dumps(test_results.get('failures', []), indent=2, ensure_ascii=False)}

错误的测试：{json.dumps(test_results.get('errors', []), indent=2, ensure_ascii=False)}

请分析并输出：
- 可能的缺陷类型和严重程度
- 缺陷描述
- 建议的修复方案
- 相关的测试用例

以JSON格式输出，包含findings数组：
- id: 唯一标识
- title: 标题
- severity: critical/high/medium/low
- defect_type: logic_error/performance/security/compatibility/usability/data_integrity
- description: 描述
- location: 位置
- code_snippet: 代码片段
- suggested_fix: 建议修复
- confidence: 置信度(0-1)
"""

    def _parse_llm_analysis(self, result: Dict[str, Any]) -> AnalysisResult:
        findings = []
        for finding_data in result.get("findings", []):
            finding = DefectFinding(
                id=finding_data.get("id", ""),
                title=finding_data.get("title", ""),
                severity=DefectSeverity(finding_data.get("severity", "medium")),
                defect_type=DefectType(finding_data.get("defect_type", "logic_error")),
                description=finding_data.get("description", ""),
                location=finding_data.get("location", ""),
                code_snippet=finding_data.get("code_snippet", ""),
                suggested_fix=finding_data.get("suggested_fix", ""),
                confidence=finding_data.get("confidence", 0.0),
                related_tests=finding_data.get("related_tests", []),
            )
            findings.append(finding)
        
        return self._build_analysis_result(findings)

    def _analyze_code_with_llm(self, code: str, file_path: str) -> AnalysisResult:
        prompt = f"""
分析以下代码，识别潜在缺陷：

文件路径：{file_path}

代码内容：
{code}

请分析并输出：
- 安全漏洞
- 逻辑错误
- 性能问题
- 代码质量问题

以JSON格式输出，包含findings数组：
- id: 唯一标识
- title: 标题
- severity: critical/high/medium/low
- defect_type: logic_error/performance/security/compatibility/usability/data_integrity
- description: 描述
- location: 位置
- code_snippet: 代码片段
- suggested_fix: 建议修复
- confidence: 置信度(0-1)
"""
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "你是一个专业的代码审查专家，能够识别代码中的缺陷和安全问题。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")
            result = json.loads(content)
            return self._parse_llm_analysis(result)
            
        except Exception as e:
            raise e

    def _build_analysis_result(self, findings: List[DefectFinding]) -> AnalysisResult:
        critical_count = sum(1 for f in findings if f.severity == DefectSeverity.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == DefectSeverity.HIGH)
        medium_count = sum(1 for f in findings if f.severity == DefectSeverity.MEDIUM)
        low_count = sum(1 for f in findings if f.severity == DefectSeverity.LOW)
        
        return AnalysisResult(
            success=True,
            findings=findings,
            total_findings=len(findings),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
        )

    def _infer_severity(self, failure: Dict[str, Any]) -> DefectSeverity:
        error_msg = failure.get("error_message", "").lower()
        if any(keyword in error_msg for keyword in ["assertionerror", "timeout", "crash"]):
            return DefectSeverity.HIGH
        if any(keyword in error_msg for keyword in ["keyerror", "indexerror", "typeerror"]):
            return DefectSeverity.MEDIUM
        return DefectSeverity.LOW

    def _infer_defect_type(self, failure: Dict[str, Any]) -> DefectType:
        error_msg = failure.get("error_message", "").lower()
        if any(keyword in error_msg for keyword in ["assertionerror"]):
            return DefectType.LOGIC_ERROR
        if "timeout" in error_msg:
            return DefectType.PERFORMANCE
        if any(keyword in error_msg for keyword in ["keyerror", "indexerror"]):
            return DefectType.DATA_INTEGRITY
        return DefectType.LOGIC_ERROR