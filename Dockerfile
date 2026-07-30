FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 1. 最小化系统依赖 (仅保留生产必需)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. 复制依赖清单 (先复制依赖利用缓存)
COPY requirements.txt ./

# 3. 安装生产依赖 (仅 requirements.txt 中的运行时依赖)
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 4. 复制应用代码 (.dockerignore 已排除敏感文件)
COPY src/ ./src/
COPY apps/ ./apps/
COPY config/ ./config/
COPY pyproject.toml ./

# 5. 创建非 root 用户并设置权限
RUN groupadd -r testai && useradd -r -g testai testai \
    && chown -R testai:testai /app

USER testai

EXPOSE 8000

# 6. 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 7. 启动命令 (修复: src.api.main -> src.platform.api)
# src.platform.api 挂载了所有 59 个业务路由
CMD ["uvicorn", "src.platform.api:app", "--host", "0.0.0.0", "--port", "8000"]