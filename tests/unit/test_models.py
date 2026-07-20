import pytest
from httpx._urlparse import urlparse
from pydantic import ValidationError

from src.governance.models import AIGovernanceResult
from src.models.assertion import Assertion
from src.models.contract import ExecutionCase, GrpcRequest, HttpRequest


def test_http_step_serialization():
    """验证 HTTP 协议的数据序列化与反序列化"""
    data = {
        "step_id": "step_001",
        "description": "用户登录测试",
        "params": {"retry": 3},
        "protocol": "http",
        "url": "https://api.test.com/login",
        "method": "POST",
        "body": {"username": "admin"},
    }

    step = HttpRequest.model_validate(data)
    assert step.protocol == "http"

    parsed_url = urlparse(str(step.url))
    assert parsed_url.netloc == "api.test.com"


def test_grpc_step_serialization():
    """验证 gRPC 协议的数据序列化与反序列化"""
    data = {
        "step_id": "step_002",
        "description": "获取用户信息",
        "protocol": "grpc",
        "proto_file_path": "/protos/user.proto",
        "service": "UserService",
        "method": "GetInfo",
        "payload": {"user_id": 123},
    }
    step = GrpcRequest.model_validate(data)
    assert step.protocol == "grpc"
    assert step.service == "UserService"


def test_test_case_polymorphism():
    """测试 TestCase 对不同协议的混合解析能力 (判别式联合的核心)"""
    case_data = {
        "case_id": "case_101",
        "name": "完整业务闭环",
        "steps": [
            {
                "step_id": "s1",
                "description": "HTTP 请求",
                "protocol": "http",
                "url": "https://api.test.com/v1",
                "method": "GET",
            },
            {
                "step_id": "s2",
                "description": "gRPC 请求",
                "protocol": "grpc",
                "proto_file_path": "a.proto",
                "service": "Svc",
                "method": "Mth",
                "payload": {},
            },
        ],
    }
    case = ExecutionCase.model_validate(case_data)
    assert len(case.steps) == 2
    assert case.steps[0].protocol == "http"
    assert case.steps[1].protocol == "grpc"


def test_schema_defense():
    """验证防御性：错误数据应抛出 Validation Error"""
    # 缺少必填字段 'service'
    invalid_data = {
        "step_id": "s_err",
        "description": "错误的GRPC",
        "protocol": "grpc",
        "proto_file_path": "a.proto",
        "method": "Mth",
        "payload": {},
    }
    with pytest.raises(ValidationError):
        GrpcRequest.model_validate(invalid_data)


def test_protocol_identification_and_parsing():
    """验证 TestCase 能否正确解析多协议混合序列，并拒绝非法协议"""
    json_data = {
        "case_id": "TC_001",
        "name": "Test Workflow",
        "steps": [
            {
                "protocol": "http",
                "step_id": "s1",
                "description": "test",
                "url": "https://api.example.com",
                "method": "GET",
            },
            {
                "protocol": "grpc",
                "step_id": "s2",
                "description": "grpc test",
                "proto_file_path": "test.proto",
                "service": "UserService",
                "method": "Login",
                "payload": {},
            },
        ],
    }
    # 验证解析成功
    case = ExecutionCase.model_validate(json_data)
    assert len(case.steps) == 2
    assert case.steps[0].protocol == "http"
    assert case.steps[1].protocol == "grpc"

    # 验证非法协议拦截
    invalid_protocol = json_data.copy()
    invalid_protocol["steps"][0]["protocol"] = "graphql"  # 目前未支持的协议
    with pytest.raises(ValidationError):
        ExecutionCase.model_validate(invalid_protocol)


def test_assertion_operator_validation():
    """验证断言操作符的严格校验"""
    # 合法操作符
    assertion_data = {"check": "status_code", "operator": "eq", "expected": 200}
    assert Assertion.model_validate(assertion_data)

    # 非法操作符 (例如: 'not_exists')
    invalid_assertion = {
        "check": "status_code",
        "operator": "not_exists",
        "expected": 200,
    }
    with pytest.raises(ValidationError):
        Assertion.model_validate(invalid_assertion)


def test_governance_result_validation():
    """验证治理结果模型的解析能力"""
    # 1. 验证合法数据
    valid_data = {
        "is_fixable": True,
        "reasoning": "缺少 Header 参数",
        "suggested_fix": {"key": "Authorization", "value": "Bearer token"},
        "confidence_score": 0.95,
    }
    result = AIGovernanceResult.model_validate(valid_data)
    assert result.confidence_score == 0.95
    assert result.is_fixable is True

    # 2. 验证边界条件 (Confidence score 越界)
    invalid_data = valid_data.copy()
    invalid_data["confidence_score"] = 1.5  # 应该在 0-1 之间
    with pytest.raises(ValidationError):
        AIGovernanceResult.model_validate(invalid_data)
