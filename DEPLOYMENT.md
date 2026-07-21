# TestAI 部署文档

**文档版本**: v1.0  
**创建日期**: 2026-07-20  
**适用环境**: 开发/测试/生产

---

## 一、环境要求

### 1.1 基础环境

| 环境 | 版本要求 | 说明 |
|------|---------|------|
| Python | ≥ 3.10 | 后端运行环境 |
| Node.js | ≥ 18.x | 前端构建环境 |
| npm/pnpm | ≥ 9.x | 依赖管理 |
| PostgreSQL | ≥ 14.x | 数据库（可选） |
| Redis | ≥ 7.x | 缓存（可选） |

### 1.2 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端（Next.js） | 3000 | 开发/生产 |
| 后端（FastAPI） | 8000 | API 服务 |
| 数据库（PostgreSQL） | 5432 | 数据存储 |
| 缓存（Redis） | 6379 | 缓存服务 |

---

## 二、目录结构

```
TestAI/                              # 仓库根目录
├── apps/                            # 应用目录
│   ├── web/                         # 前端 (Next.js)
│   │   ├── src/                     # 前端源码
│   │   ├── package.json             # 前端依赖
│   │   └── next.config.js           # Next.js 配置
│   └── server/                      # 后端 (FastAPI)
│       ├── main.py                  # 后端入口
│       └── pyproject.toml           # 后端依赖
├── src/                             # 核心后端源码
├── tests/                           # 测试代码
├── scripts/                         # 部署脚本
├── .github/workflows/               # CI/CD 配置
├── package.json                     # Monorepo 统一脚本
└── start.bat                        # 本地启动脚本（Windows）
```

---

## 三、本地开发环境

### 3.1 安装依赖

```bash
# 安装前端依赖
cd apps/web
npm install

# 安装后端依赖
cd apps/server
pip install -e .
```

### 3.2 启动服务

**方式一：使用统一启动脚本**
```bash
# Windows
start.bat

# 选择操作：
# 1. 启动前端 (Next.js)
# 2. 启动后端 (FastAPI)
# 3. 启动前后端 (同时)
```

**方式二：手动启动**
```bash
# 启动前端（终端1）
cd apps/web
npm run dev

# 启动后端（终端2）
cd apps/server
python main.py
```

### 3.3 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3000 | Next.js 开发服务器 |
| 后端 API | http://localhost:8000 | FastAPI 服务 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| API 文档 | http://localhost:8000/redoc | ReDoc |

---

## 四、构建与部署

### 4.1 前端构建

```bash
cd apps/web
npm run build
```

构建产物输出到 `apps/web/.next/` 目录。

### 4.2 后端打包

```bash
cd apps/server
python -m build
```

### 4.3 Docker 容器化

**Dockerfile（前端）**
```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM node:18-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
RUN npm ci --only=production
EXPOSE 3000
CMD ["npm", "start"]
```

**Dockerfile（后端）**
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY apps/server/pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .
EXPOSE 8000
CMD ["python", "apps/server/main.py"]
```

**docker-compose.yml**
```yaml
version: '3.8'
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile.web
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://server:8000
    depends_on:
      - server

  server:
    build:
      context: .
      dockerfile: Dockerfile.server
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/testai
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:14
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=testai
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 4.4 环境变量配置

**前端环境变量（apps/web/.env）**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=TestAI
```

**后端环境变量（.env）**
```env
# 数据库配置
DATABASE_URL=postgresql://postgres:password@localhost:5432/testai

# Redis 配置
REDIS_URL=redis://localhost:6379

# 安全配置
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 日志配置
LOG_LEVEL=INFO

# 工作流配置
WORKFLOW_MAX_RETRIES=3
WORKFLOW_TIMEOUT=300
```

---

## 五、CI/CD 流程

### 5.1 GitHub Actions 配置

**文件**: `.github/workflows/deploy.yml`

```yaml
name: Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Install dependencies
        run: |
          pip install -e apps/server
          npm install --prefix apps/web
      - name: Run tests
        run: python -m pytest tests/governance/ -v
      - name: Run mutation tests
        run: python tests/utils/custom_mutation_test.py --target src/governance/ --test all

  build-frontend:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm install --prefix apps/web
      - name: Build frontend
        run: npm run build --prefix apps/web
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-build
          path: apps/web/.next/

  deploy:
    runs-on: ubuntu-latest
    needs: [test, build-frontend]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: |
          echo "Deploying to production..."
          # Add your deployment commands here
```

---

## 六、数据库初始化

### 6.1 创建数据库

```sql
CREATE DATABASE testai;
CREATE USER testai_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE testai TO testai_user;
```

### 6.2 迁移脚本

```bash
# 创建迁移（如需）
cd apps/server
alembic init migrations
```

---

## 七、监控与日志

### 7.1 日志配置

后端日志输出到 `logs/` 目录，包含：
- `app.log` - 应用日志
- `error.log` - 错误日志
- `access.log` - 访问日志

### 7.2 健康检查

```bash
# 后端健康检查
curl http://localhost:8000/health

# 响应示例
{
  "status": "healthy",
  "timestamp": "2026-07-20T10:00:00Z",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "workflow": "healthy"
  }
}
```

---

## 八、故障排查

### 8.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 前端无法连接后端 | CORS 配置错误 | 检查后端 CORS 配置，确保允许前端域名 |
| 后端启动失败 | PYTHONPATH 错误 | 确保项目根目录在 PYTHONPATH 中 |
| 测试失败 | 代码污染 | 运行 `python tests/utils/custom_mutation_test.py` 前确保无残留变异 |
| 构建失败 | 依赖缺失 | 重新安装依赖 `npm install` / `pip install` |

### 8.2 调试命令

```bash
# 检查后端 API 状态
curl http://localhost:8000/health

# 查看后端日志
tail -f logs/app.log

# 检查前端构建错误
cd apps/web && npm run build --verbose
```

---

## 九、安全注意事项

1. **环境变量**: 敏感配置（数据库密码、密钥）必须通过环境变量传递，禁止硬编码
2. **认证授权**: 生产环境必须启用认证，限制 API 访问权限
3. **HTTPS**: 生产环境必须使用 HTTPS
4. **CORS**: 限制允许的源域名，禁止使用 `*`
5. **日志**: 禁止在日志中记录敏感信息（密码、token）

---

## 十、版本升级

### 10.1 升级流程

1. 更新代码
2. 运行测试验证
3. 构建新版本
4. 部署到测试环境
5. 验证功能
6. 部署到生产环境

### 10.2 回滚流程

1. 停止当前服务
2. 部署上一版本
3. 验证功能恢复
4. 分析问题原因

---

## 十一、附录

### 11.1 常用命令

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行变异测试
python tests/utils/custom_mutation_test.py --target src/governance/ --test all

# 前端开发
cd apps/web && npm run dev

# 后端开发
cd apps/server && python main.py

# 前端构建
cd apps/web && npm run build

# Docker 启动
docker-compose up -d

# Docker 查看日志
docker-compose logs -f
```

### 11.2 配置文件清单

| 文件 | 用途 |
|------|------|
| `.env` | 后端环境变量 |
| `apps/web/.env` | 前端环境变量 |
| `apps/web/next.config.js` | Next.js 配置 |
| `apps/server/pyproject.toml` | 后端依赖配置 |
| `docker-compose.yml` | Docker 容器配置 |
