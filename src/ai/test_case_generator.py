import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class TestCaseType(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    API = "api"
    UI = "ui"
    E2E = "e2e"


@dataclass
class GeneratedTestCase:
    id: str
    name: str
    type: TestCaseType
    description: str
    steps: List[str]
    expected_results: List[str]
    priority: str = "medium"
    tags: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class GenerationResult:
    success: bool
    test_cases: List[GeneratedTestCase] = field(default_factory=list)
    error_message: str = ""
    total_generated: int = 0
    fallback_used: bool = False


class TestCaseGenerator:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key

    def generate_from_spec(self, spec: Dict[str, Any]) -> GenerationResult:
        if self.use_fallback:
            return self._generate_fallback(spec)
        
        try:
            return self._generate_with_llm(spec)
        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"LLM generation failed: {str(e)}",
                fallback_used=True,
                test_cases=self._generate_fallback(spec).test_cases,
            )

    def _generate_with_llm(self, spec: Dict[str, Any]) -> GenerationResult:
        prompt = self._build_prompt(spec)
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "你是一个专业的测试用例生成器，能够根据需求规范生成高质量的测试用例。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")
            result = json.loads(content)
            return self._parse_llm_result(result)
            
        except Exception as e:
            raise e

    def _generate_fallback(self, spec: Dict[str, Any]) -> GenerationResult:
        test_cases = []
        spec_name = spec.get("name", "unnamed")
        spec_type = spec.get("type", "api")
        endpoints = spec.get("endpoints", [])
        
        if spec_type == "api" and endpoints:
            for endpoint in endpoints:
                test_cases.extend(self._generate_api_test_cases(endpoint))
        elif spec_type == "unit":
            test_cases.extend(self._generate_unit_test_cases(spec))
        elif spec_type == "ui":
            test_cases.extend(self._generate_ui_test_cases(spec))
        
        return GenerationResult(
            success=True,
            test_cases=test_cases,
            total_generated=len(test_cases),
            fallback_used=True,
        )

    def _build_prompt(self, spec: Dict[str, Any]) -> str:
        return f"""
根据以下需求规范生成测试用例：

名称：{spec.get('name', '')}
类型：{spec.get('type', '')}
描述：{spec.get('description', '')}

接口列表：{json.dumps(spec.get('endpoints', []), indent=2, ensure_ascii=False)}

请生成以下类型的测试用例：
1. 正向测试用例
2. 负向测试用例
3. 边界条件测试用例
4. 异常场景测试用例

请以JSON格式输出，包含：
- test_cases: 测试用例列表
  - id: 唯一标识
  - name: 测试用例名称
  - type: 测试类型（unit/api/ui/e2e）
  - description: 描述
  - steps: 测试步骤列表
  - expected_results: 预期结果列表
  - priority: 优先级（high/medium/low）
  - tags: 标签列表
  - preconditions: 前置条件列表
"""

    def _parse_llm_result(self, result: Dict[str, Any]) -> GenerationResult:
        test_cases = []
        for tc_data in result.get("test_cases", []):
            test_case = GeneratedTestCase(
                id=tc_data.get("id", ""),
                name=tc_data.get("name", ""),
                type=TestCaseType(tc_data.get("type", "unit")),
                description=tc_data.get("description", ""),
                steps=tc_data.get("steps", []),
                expected_results=tc_data.get("expected_results", []),
                priority=tc_data.get("priority", "medium"),
                tags=tc_data.get("tags", []),
                preconditions=tc_data.get("preconditions", []),
            )
            test_cases.append(test_case)
        
        return GenerationResult(
            success=True,
            test_cases=test_cases,
            total_generated=len(test_cases),
        )

    def _generate_api_test_cases(self, endpoint: Dict[str, Any]) -> List[GeneratedTestCase]:
        cases = []
        method = endpoint.get("method", "GET")
        path = endpoint.get("path", "/")
        params = endpoint.get("params", [])
        body = endpoint.get("body", {})
        
        cases.append(GeneratedTestCase(
            id=f"api_{method.lower()}_{path.replace('/', '_')}_success",
            name=f"{method} {path} - 正常请求",
            type=TestCaseType.API,
            description=f"测试{method} {path}接口的正常请求",
            steps=[
                f"构造{method}请求到{path}",
                f"设置必要的请求参数",
                "发送请求",
                "验证响应",
            ],
            expected_results=[
                "响应状态码为200",
                "响应数据结构正确",
                "响应时间小于1秒",
            ],
            priority="high",
            tags=["api", "positive"],
        ))
        
        cases.append(GeneratedTestCase(
            id=f"api_{method.lower()}_{path.replace('/', '_')}_invalid_params",
            name=f"{method} {path} - 参数校验失败",
            type=TestCaseType.API,
            description=f"测试{method} {path}接口的参数校验",
            steps=[
                f"构造{method}请求到{path}",
                "传入无效参数",
                "发送请求",
                "验证响应",
            ],
            expected_results=[
                "响应状态码为400",
                "返回清晰的错误信息",
            ],
            priority="medium",
            tags=["api", "negative"],
        ))
        
        if params:
            for param in params:
                cases.append(GeneratedTestCase(
                    id=f"api_{method.lower()}_{path.replace('/', '_')}_missing_{param['name']}",
                    name=f"{method} {path} - 缺少{param['name']}参数",
                    type=TestCaseType.API,
                    description=f"测试{method} {path}接口缺少{param['name']}参数的情况",
                    steps=[
                        f"构造{method}请求到{path}",
                        f"不传入{param['name']}参数",
                        "发送请求",
                        "验证响应",
                    ],
                    expected_results=[
                        "响应状态码为400",
                        f"提示缺少{param['name']}参数",
                    ],
                    priority="medium",
                    tags=["api", "negative"],
                ))
        
        return cases

    def _generate_unit_test_cases(self, spec: Dict[str, Any]) -> List[GeneratedTestCase]:
        cases = []
        functions = spec.get("functions", [])
        
        for func in functions:
            cases.append(GeneratedTestCase(
                id=f"unit_{func.get('name', '')}_normal",
                name=f"{func.get('name', '')} - 正常参数",
                type=TestCaseType.UNIT,
                description=f"测试{func.get('name', '')}函数的正常参数",
                steps=[
                    f"调用{func.get('name', '')}函数",
                    "传入有效参数",
                    "验证返回值",
                ],
                expected_results=[
                    "函数执行成功",
                    "返回值符合预期",
                ],
                priority="high",
                tags=["unit", "positive"],
            ))
            
            cases.append(GeneratedTestCase(
                id=f"unit_{func.get('name', '')}_invalid",
                name=f"{func.get('name', '')} - 无效参数",
                type=TestCaseType.UNIT,
                description=f"测试{func.get('name', '')}函数的无效参数",
                steps=[
                    f"调用{func.get('name', '')}函数",
                    "传入无效参数",
                    "验证错误处理",
                ],
                expected_results=[
                    "函数抛出异常",
                    "异常信息清晰",
                ],
                priority="medium",
                tags=["unit", "negative"],
            ))
        
        return cases

    def _generate_ui_test_cases(self, spec: Dict[str, Any]) -> List[GeneratedTestCase]:
        cases = []
        pages = spec.get("pages", [])
        
        for page in pages:
            cases.append(GeneratedTestCase(
                id=f"ui_{page.get('name', '')}_load",
                name=f"{page.get('name', '')} - 页面加载",
                type=TestCaseType.UI,
                description=f"测试{page.get('name', '')}页面加载",
                steps=[
                    "导航到页面",
                    "等待页面加载完成",
                    "验证页面元素",
                ],
                expected_results=[
                    "页面成功加载",
                    "所有元素可见",
                    "页面加载时间小于3秒",
                ],
                priority="high",
                tags=["ui", "positive"],
            ))
        
        return cases

    def generate_from_code(self, code: str, language: str = "python") -> GenerationResult:
        spec = self._analyze_code(code, language)
        return self.generate_from_spec(spec)

    def _analyze_code(self, code: str, language: str) -> Dict[str, Any]:
        functions = []
        
        if language == "python":
            func_pattern = r"def\s+(\w+)\s*\(([^)]*)\)"
            matches = re.findall(func_pattern, code)
            for name, params in matches:
                functions.append({
                    "name": name,
                    "params": [p.strip() for p in params.split(",") if p.strip()],
                })
        
        return {
            "name": "代码分析生成",
            "type": "unit",
            "description": f"从{language}代码自动生成的测试用例",
            "functions": functions,
        }