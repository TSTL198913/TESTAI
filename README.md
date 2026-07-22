# TestAI

[![CI/CD](https://github.com/TSTL198913/TESTAI/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/TSTL198913/TESTAI/actions/workflows/ci-cd.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AI 驱动的自治测试与智能诊断平台，为企业级应用提供全方位的自动化测试能力与智能化治理闭环。

## 核心特性

- **多协议测试引擎**：支持 HTTP、gRPC 协议的自动化测试，模块化设计便于扩展
- **AI 治理闭环**：诊断→修复→审批→收敛验证，完整的智能治理流程，内置安全护栏
- **并发安全与熔断恢复**：线程安全的单例模式、文件锁机制、熔断降级策略
- **结构化日志与健康监控**：JSON 格式日志输出，支持 ELK/Datadog 等现代监控体系
- **CI/CD 多环境矩阵**：Ubuntu/Windows 跨平台支持，Python 3.10/3.11 多版本测试

## 架构速览

```
┌──────────────────────────────────────────────────────────────────┐
│                     Client / CI/CD                               │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP/gRPC
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FastAPI API Layer                           │
│    (src/api/main.py)                                             │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Workflow Orchestrator                         │
│    (src/governance/orchestrator.py)                              │
└───────────────────────────┬──────────────────────────────────────┘
                            │
    ┌───────────────────────┼───────────────────────┐
    ▼                       ▼                       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Processor  │     │  Executor   │     │  Validator  │
│   Pipeline  │     │ (HTTP/gRPC) │     │  (断言)     │
└─────────────┘     └─────────────┘     └─────────────┘
    │                       │                       │
    └───────────────────────┼───────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   AI Governance Engine                            │
│    (src/governance/agent.py, tracker.py, approval.py)            │
│    诊断 → 修复 → 审批 → 收敛验证                                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                  │
│    SQLite (审计日志) / MongoDB (测试数据) / Redis (缓存)          │
└──────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.10+
- pip 21.0+

### 1. 配置虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境 (Windows)
venv\Scripts\activate

# 激活虚拟环境 (Linux/Mac)
source venv/bin/activate
```

### 2. 安装依赖

```bash
# 升级 pip
python -m pip install --upgrade pip

# 安装项目及其开发依赖
pip install -e ".[dev]"
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置 API Key 等敏感信息
```

### 4. 运行测试

```bash
# 运行完整测试套件
python -m pytest tests/ -v

# 运行指定模块的测试
python -m pytest tests/governance/test_approval.py -v

# 生成覆盖率报告
python -m pytest tests/ --cov=src --cov-report=html
```

### 5. 启动服务

```bash
# 启动 API 服务
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# 启动 Worker
celery -A src.worker.celery_app worker --loglevel=info
```

## API 概览

### 测试执行

| 端点 | 方法 | 描述 |
|------|------|------|
| `/execute` | POST | 执行测试流水线，返回任务ID和追踪ID |

**请求示例**：
```json
{
  "protocol": "http",
  "method": "GET",
  "url": "https://api.example.com/test",
  "headers": {"Authorization": "Bearer token"},
  "expected_status": 200,
  "expected_body": {"status": "ok"}
}
```

**响应示例**：
```json
{
  "status": "queued",
  "task_id": "ad544224-0dc0-4096-a44b-f4b7942fc1c2",
  "trace_id": "abc12345",
  "message": "流水线已入队，请关注 MongoDB 数据更新"
}
```

## 测试体系

TestAI 采用分层测试策略，确保各层级的质量保障：

| 测试层级 | 数量 | 目录 | 覆盖范围 |
|---------|------|------|---------|
| **单元测试** | 18 | `tests/unit/` | 核心模型、处理器、管道逻辑 |
| **治理测试** | 145 | `tests/governance/` | 审批机制、安全边界、并发控制、收敛验证 |
| **集成测试** | 2 | `tests/integration/` | API 层、Worker 层、全链路生命周期 |
| **性能测试** | 1 | `tests/performance/` | 压力测试、稳定性验证 |

### 测试命令

```bash
# 运行单元测试
python -m pytest tests/unit/ -v

# 运行治理测试
python -m pytest tests/governance/ -v

# 运行集成测试
python -m pytest tests/integration/ -v

# 运行性能测试
python -m pytest tests/performance/ -v --timeout=120

# 运行完整套件（排除已知问题）
python -m pytest tests/ --ignore=tests/governance/test_tracker.py -v
```

## CI/CD 流水线

项目采用 GitHub Actions 实现自动化 CI/CD：

```
推送代码 → 多平台测试 (Ubuntu/Windows) → 安全扫描 (bandit/pip-audit)
         → 代码质量检查 (pylint/mypy) → 构建 (Python包/Docker镜像)
         → 部署 (preview/staging/production)
```

## 贡献指南

### 开发流程

1. Fork 项目并克隆到本地
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 编写代码和测试用例
4. 运行测试确保通过
5. 提交代码并创建 Pull Request

### 代码规范

- 遵循 PEP8 编码规范
- 使用 type hints 进行类型标注
- 编写单元测试覆盖核心逻辑
- 提交信息遵循 Conventional Commits

### 提交信息格式

```
<type>(<scope>): <description>

<optional body>

<optional footer>
```

常用类型：
- `feat`: 新功能
- `fix`: 修复 Bug
- `docs`: 文档更新
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具相关

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
<!-- Auto-trigger CI -->

<!-- DevOps checks updated -->

<!-- DevOps gates updated 20260722102446 -->

<!-- DevOps gates updated 20260722102459 -->

<!-- CI gate test 20260722102844 -->

<!-- CI gate test 20260722102900 -->
