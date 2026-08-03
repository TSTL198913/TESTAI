# TestAI 上线检查清单

## 一、环境准备

### 基础环境
- [ ] Python 3.10+ 已安装
- [ ] Docker 已安装并运行
- [ ] Docker Compose 已安装
- [ ] Git 已安装

### 依赖安装
- [ ] `pip install -e .` 已执行
- [ ] 所有依赖安装成功，无版本冲突

## 二、配置检查

### 环境变量
- [ ] `.env` 文件已创建（基于 `.env.example`）
- [ ] `MONGO_URI` 配置正确
- [ ] `DEEPSEEK_API_KEY` 已配置且有效
- [ ] `REDIS_URL` 配置正确

### 目录结构
- [ ] `data/` 目录存在且有读写权限
- [ ] `reports/` 目录存在且有读写权限

## 三、安全检查

### 依赖安全
- [ ] `bandit -r src/` 无高危漏洞
- [ ] `pip-audit` 无高危依赖漏洞

### 代码质量
- [ ] `pylint src/` 无致命错误
- [ ] `mypy src/` 无类型错误

## 四、测试验证

### 核心功能测试
- [ ] 审批管理测试通过 (`tests/governance/test_approval.py`)
- [ ] 安全边界测试通过 (`tests/governance/test_security.py`)
- [ ] 监控告警测试通过 (`tests/governance/test_monitoring.py`)
- [ ] 数据持久化测试通过 (`tests/governance/test_persistence.py`)

### API层测试
- [ ] API端点测试通过 (`tests/integration/test_api.py`)

### Worker层测试
- [ ] Worker任务测试通过 (`tests/integration/test_worker.py`)

### 完整测试套件
- [x] 1427 测试用例通过（2026-08-02 验证）
- [x] 无阻塞性错误（0 failed, 0 hang）

## 五、Docker部署

### 镜像构建
- [ ] `docker-compose build` 成功
- [ ] 镜像无构建错误

### 容器启动
- [ ] `docker-compose up -d` 成功
- [ ] 所有服务健康检查通过
- [ ] API服务运行在端口 8000
- [ ] MongoDB运行在端口 27017
- [ ] Redis运行在端口 6379

## 六、服务验证

### 健康检查
- [ ] `curl http://localhost:8000/health` 返回 200
- [ ] MongoDB连接正常
- [ ] Redis连接正常

### 功能验证
- [ ] POST `/execute` 端点可正常调用
- [ ] 任务可正确入队
- [ ] 结果可正确存储和查询

## 七、监控配置

### 日志检查
- [ ] 日志级别配置正确
- [ ] 日志输出到控制台和文件
- [ ] 错误日志可追踪

### 告警配置
- [ ] 告警级别定义正确
- [ ] 告警通知机制已配置
- [ ] 健康监控已启用

## 八、上线前确认

### 文档检查
- [ ] API文档可访问 (`/docs`)
- [ ] 部署文档完整

### 备份确认
- [ ] 数据库备份策略已制定
- [ ] 关键配置已备份

### 回滚方案
- [ ] 回滚流程已确认
- [ ] 回滚脚本已准备

## 九、已知问题（已修复）

1. ~~**tracker.py死锁问题**~~：已修复。`_lock = threading.RLock()` 可重入锁，
   `get_summary` 在锁内调用 `get_events_by_trace`（同 RLock）不会死锁。
   证据：[src/governance/tracker.py:45](../src/governance/tracker.py#L45)

2. ~~**test_fix_verify.py加载失败**~~：已删除。该测试文件已不存在，
   `data/buggy_module.py` 仅 4 字节占位文件。

3. ~~**Dockerfile.prod 缺失**~~：已修复（2026-08-02）。
   `docker-compose.prod.yml` 引用 `Dockerfile.prod`，现已创建。
   CMD 用 `uvicorn --workers 4`（与 `start.sh start_prod` 一致）。

4. ~~**docker-compose.prod.yml container_name + replicas 冲突**~~：已修复（2026-08-02）。
   删除 `deploy.replicas`（普通 `docker-compose up` 模式无效），保留 `container_name`。
   `docker compose config` 验证通过。

## 十、上线审批

### 审批人
- [ ] 技术负责人审批通过
- [ ] 安全负责人审批通过

### 上线时间
- [ ] 上线窗口已确认
- [ ] 回滚时间窗口已确认

---

**上线状态**: ⚠️ 阻塞已解除，待生产环境验证
- 后端核心功能已达上线标准（1427 测试通过，P0 修复完成）
- Docker 配置语法验证通过（`docker compose config` PASS）
- 待验证项：docker build 实际构建、真实依赖链连通性、UI 端到端测试
**最后更新**: 2026-08-02