# TestAI Monorepo 架构规范

## 1. 架构原则

### 1.1 Monorepo 定义
将多个独立的应用（前端、后端、工具）放在同一个 Git 仓库中管理，共享配置、工具链和 CI/CD 流程。

### 1.2 核心原则
- **目录隔离**：不同应用必须放在独立目录，禁止跨目录引用
- **依赖独立**：每个应用有独立的依赖管理
- **统一构建**：通过 workspace 实现统一构建和测试
- **规范一致**：统一的代码风格、提交规范、CI/CD 流程

## 2. 目录结构

```
TestAI/                              # 仓库根目录
├── apps/                            # 应用目录（核心）
│   ├── web/                         # 前端应用 (Next.js)
│   │   ├── src/                     # 前端源码
│   │   ├── package.json             # 前端依赖
│   │   └── ...                      # 其他前端配置
│   └── server/                      # 后端应用 (FastAPI)
│       ├── src/                     # 后端源码
│       ├── pyproject.toml           # 后端依赖
│       └── ...                      # 其他后端配置
├── packages/                        # 共享包目录（可选）
│   └── common/                      # 前后端共享代码
├── docs/                            # 文档目录
├── tests/                           # 测试目录（集成测试）
├── scripts/                         # 脚本目录
├── .github/workflows/               # CI/CD 配置
├── .gitignore                       # 全局忽略
├── package.json                     # 根目录配置（pnpm workspace）
├── turbo.json                       # Turborepo 配置（可选）
└── README.md                        # 项目说明
```

## 3. 目录边界约束

### 3.1 apps/web（前端）
- ✅ 允许：TypeScript、React、Next.js、Tailwind CSS
- ✅ 允许：与 apps/server 的 API 通信
- ❌ 禁止：Python 文件
- ❌ 禁止：直接引用 apps/server 的代码
- ❌ 禁止：Node/Next 产物出现在 apps/server

### 3.2 apps/server（后端）
- ✅ 允许：Python、FastAPI、SQLAlchemy
- ✅ 允许：提供 RESTful API
- ❌ 禁止：JavaScript/TypeScript 文件
- ❌ 禁止：直接引用 apps/web 的代码
- ❌ 禁止：Python 编译产物出现在 apps/web

### 3.3 packages（共享包）
- ✅ 允许：TypeScript/Python 共享工具函数
- ✅ 允许：类型定义、常量、工具类
- ❌ 禁止：业务逻辑
- ❌ 禁止：依赖于特定框架的代码

## 4. 依赖管理规范

### 4.1 前端依赖
- 使用 npm 作为包管理器
- 依赖声明在 `apps/web/package.json`
- 禁止在根目录安装前端依赖

### 4.2 后端依赖
- 使用 pip/pipenv/uv 作为包管理器
- 依赖声明在 `apps/server/pyproject.toml` 或 `requirements.txt`
- 禁止在根目录安装后端依赖

### 4.3 工作区配置
- 使用 pnpm workspace 管理多应用依赖
- 根目录 `package.json` 仅包含 workspace 配置和脚本

## 5. 构建与运行规范

### 5.1 前端构建
```bash
# 开发模式
cd apps/web && npm run dev

# 生产构建
cd apps/web && npm run build

# 启动生产服务
cd apps/web && npm run start
```

### 5.2 后端构建
```bash
# 开发模式
cd apps/server && uvicorn src.platform.api:app --reload

# 生产构建（编译/打包）
cd apps/server && python -m build
```

### 5.3 统一脚本
根目录提供统一入口脚本：
- `scripts/start.sh` - Linux/macOS
- `scripts/start.bat` - Windows

## 6. CI/CD 规范

### 6.1 前端流水线
- ✅ 安装依赖（npm install）
- ✅ 类型检查（tsc --noEmit）
- ✅ 构建验证（npm run build）
- ✅ 单元测试（npm test）

### 6.2 后端流水线
- ✅ 安装依赖（pip install）
- ✅ 代码检查（flake8/mypy）
- ✅ 单元测试（pytest）
- ✅ 变异测试（mutmut）

### 6.3 部署流水线
- ✅ 前端构建产物上传
- ✅ 后端 Docker 镜像构建
- ✅ 部署到目标环境

## 7. 代码规范

### 7.1 前端代码规范
- 语言：TypeScript
- 风格：ESLint + Prettier
- 框架：Next.js 14 App Router
- 组件：React Function Component

### 7.2 后端代码规范
- 语言：Python 3.11+
- 风格：flake8 + black
- 类型：mypy
- 框架：FastAPI

## 8. 验收标准

### 8.1 目录隔离验收
- [ ] apps/web 中无 .py 文件
- [ ] apps/server 中无 .js/.ts 文件
- [ ] 根目录 src/ 已清理或重定向
- [ ] 各应用有独立的 package.json/pyproject.toml

### 8.2 构建验收
- [ ] 前端独立构建成功
- [ ] 后端独立启动成功
- [ ] 前后端通信正常（API 代理/CORS）

### 8.3 测试验收
- [ ] 前端单元测试通过
- [ ] 后端单元测试通过
- [ ] 集成测试通过
- [ ] 变异测试 Kill Rate ≥ 80%