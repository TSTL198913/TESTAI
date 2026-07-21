# TestAI 运维手册

**文档编号**: OPS-2026-001  
**版本**: v1.0  
**日期**: 2026-07-21  
**适用环境**: 开发/预生产/生产

---

## 一、文档概述

本文档提供 TestAI 平台的运维操作指南，包括服务管理、监控告警、故障排查、备份恢复等内容。

---

## 二、环境架构

### 2.1 服务组件

| 服务 | 端口 | 说明 |
|------|------|------|
| API | 8000 | FastAPI 接口服务 |
| Worker | - | Celery 任务执行 |
| MongoDB | 27017 | 数据存储 |
| Redis | 6379 | 缓存/消息队列 |
| Prometheus | 9090 | 指标采集 |
| Grafana | 3000 | 可视化监控 |
| Nginx | 80/443 | 反向代理（生产） |

### 2.2 目录结构

```
TestAI/
├── data/              # 数据目录（按环境隔离）
│   ├── dev/
│   ├── staging/
│   └── prod/
├── reports/           # 报告输出目录
│   ├── dev/
│   ├── staging/
│   └── prod/
├── monitoring/        # 监控配置
│   ├── prometheus.yml
│   ├── alert_rules.yml
│   └── grafana/
├── docker-compose*.yml # 环境部署配置
└── .env               # 环境变量
```

---

## 三、服务管理

### 3.1 启动服务

**开发环境**:
```bash
docker-compose up -d
```

**预生产环境**:
```bash
docker-compose -f docker-compose.staging.yml up -d
```

**生产环境**:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### 3.2 停止服务

```bash
docker-compose -f docker-compose.prod.yml down
```

### 3.3 查看服务状态

```bash
docker-compose -f docker-compose.prod.yml ps
```

### 3.4 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.prod.yml logs -f

# 查看指定服务日志
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f worker
```

### 3.5 重启服务

```bash
# 重启单个服务
docker-compose -f docker-compose.prod.yml restart api

# 重启所有服务
docker-compose -f docker-compose.prod.yml restart
```

---

## 四、健康检查

### 4.1 API 健康检查

```bash
curl http://localhost:8000/health
```

**预期响应**:
```json
{
  "status": "healthy",
  "timestamp": "2026-07-21T10:00:00Z",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "workflow": "healthy"
  }
}
```

### 4.2 MongoDB 健康检查

```bash
docker exec testai-mongo-prod mongosh --eval "db.adminCommand('ping')"
```

### 4.3 Redis 健康检查

```bash
docker exec testai-redis-prod redis-cli ping
```

---

## 五、监控告警

### 5.1 监控访问地址

| 服务 | 地址 |
|------|------|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

### 5.2 告警规则

详见 [monitoring/alert_rules.yml](file:///d:/workspace/TestAI/monitoring/alert_rules.yml)

### 5.3 告警级别

| 级别 | 说明 | 处理时限 |
|------|------|---------|
| **CRITICAL** | 服务不可用、数据丢失、安全事件 | 5分钟内响应 |
| **WARNING** | 性能下降、资源紧张、测试失败率高 | 15分钟内响应 |

### 5.4 告警通知渠道

- **邮件**: 通过 SMTP 发送告警邮件
- **钉钉**: 通过钉钉机器人推送告警
- **飞书**: 通过飞书机器人推送告警

配置方式: 在 `.env` 文件中设置相关环境变量。

---

## 六、备份恢复

### 6.1 MongoDB 备份

```bash
# 创建备份目录
mkdir -p backups/mongo/$(date +%Y%m%d)

# 执行备份
docker exec testai-mongo-prod mongodump \
  --db testai_prod \
  --out /backup/$(date +%Y%m%d)

# 复制到宿主机
docker cp testai-mongo-prod:/backup/$(date +%Y%m%d) backups/mongo/
```

### 6.2 MongoDB 恢复

```bash
# 复制备份到容器
docker cp backups/mongo/20260721 testai-mongo-prod:/backup/

# 执行恢复
docker exec testai-mongo-prod mongorestore \
  --db testai_prod \
  /backup/20260721/testai_prod
```

### 6.3 Redis 备份

```bash
docker exec testai-redis-prod redis-cli SAVE
docker cp testai-redis-prod:/data/dump.rdb backups/redis/dump_$(date +%Y%m%d).rdb
```

### 6.4 Redis 恢复

```bash
docker cp backups/redis/dump_20260721.rdb testai-redis-prod:/data/dump.rdb
docker-compose -f docker-compose.prod.yml restart redis
```

---

## 七、日志管理

### 7.1 日志位置

| 服务 | 日志路径 |
|------|---------|
| API | `data/prod/app.log` |
| API 错误 | `data/prod/error.log` |
| Worker | 容器日志 |

### 7.2 日志格式

所有日志采用 JSON 格式输出，便于日志系统采集和分析：

```json
{
  "timestamp": "2026-07-21T10:00:00Z",
  "level": "INFO",
  "module": "src.platform.api",
  "message": "Request processed",
  "request_id": "abc123",
  "status_code": 200,
  "duration_ms": 123
}
```

### 7.3 日志清理

```bash
# 保留最近7天的日志
find data/prod -name "*.log" -mtime +7 -delete
```

---

## 八、性能调优

### 8.1 API 调优

- **增加 API 实例数**: 修改 `docker-compose.prod.yml` 中的 `replicas`
- **调整工作线程**: 修改启动命令中的 `--workers` 参数
- **启用 Gunicorn**: 使用 Gunicorn 替代 uvicorn 作为生产服务器

### 8.2 Worker 调优

- **调整并发数**: 修改 `--concurrency` 参数
- **增加 Worker 实例**: 修改 `docker-compose.prod.yml` 中的 `replicas`

### 8.3 数据库调优

- **MongoDB**: 创建索引、调整连接池大小
- **Redis**: 启用持久化、调整内存策略

---

## 九、安全管理

### 9.1 环境变量管理

- 敏感配置（密码、密钥）必须通过环境变量传递
- 禁止硬编码敏感信息
- 生产环境必须使用独立的密钥

### 9.2 访问控制

- API 接口必须启用认证
- 监控服务必须配置访问密码
- 禁止在生产环境暴露管理端口

### 9.3 HTTPS

生产环境必须启用 HTTPS，配置方式:
1. 获取 SSL 证书
2. 配置 Nginx 反向代理
3. 更新 `monitoring/nginx/nginx.conf`

---

## 十、常见问题排查

### 10.1 API 无法启动

**可能原因**:
- 端口被占用
- 数据库连接失败
- 环境变量配置错误

**排查步骤**:
```bash
# 查看日志
docker-compose -f docker-compose.prod.yml logs api

# 检查端口占用
netstat -tlnp | grep 8000

# 检查数据库连接
docker exec testai-mongo-prod mongosh --eval "db.adminCommand('ping')"
```

### 10.2 Worker 不执行任务

**可能原因**:
- Redis 连接失败
- 任务队列阻塞
- Worker 进程异常

**排查步骤**:
```bash
# 查看 Worker 日志
docker-compose -f docker-compose.prod.yml logs worker

# 检查 Redis 连接
docker exec testai-redis-prod redis-cli ping

# 检查任务队列
docker exec testai-redis-prod redis-cli LLEN celery
```

### 10.3 数据库连接超时

**可能原因**:
- MongoDB 服务未启动
- 网络连接问题
- 连接池耗尽

**排查步骤**:
```bash
# 检查 MongoDB 状态
docker-compose -f docker-compose.prod.yml ps mongo

# 检查网络连接
docker exec testai-api-prod ping mongo -c 3

# 检查连接池状态
curl http://localhost:8000/health
```

### 10.4 内存使用率过高

**排查步骤**:
```bash
# 查看容器内存使用
docker stats

# 查看进程内存使用
docker exec testai-api-prod ps aux --sort=-%mem

# 分析内存泄漏
docker exec testai-api-prod python -m memory_profiler
```

---

## 十一、紧急联系

| 角色 | 联系方式 |
|------|---------|
| 技术负责人 | ops@testai.com |
| 值班工程师 | oncall@testai.com |
| 应急热线 | +86-10-12345678 |

---

## 附录

### A. 常用命令速查

```bash
# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f api

# 重启服务
docker-compose -f docker-compose.prod.yml restart api

# 健康检查
curl http://localhost:8000/health

# 备份数据库
docker exec testai-mongo-prod mongodump --db testai_prod --out /backup/$(date +%Y%m%d)
```

### B. 环境变量清单

| 变量 | 说明 | 默认值 |
|------|------|--------|
| MONGO_URI | MongoDB 连接地址 | mongodb://mongo:27017 |
| REDIS_URL | Redis 连接地址 | redis://redis:6379/0 |
| ENVIRONMENT | 运行环境 | production |
| LOG_LEVEL | 日志级别 | INFO |
| SECRET_KEY | JWT 密钥 | - |

---

**文档版本历史**:

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| v1.0 | 2026-07-21 | 初始版本 |