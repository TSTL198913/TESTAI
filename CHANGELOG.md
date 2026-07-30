# Changelog

All notable changes to this project will be documented in this file.

## [v0.2.0] - 2026-03-18

### Added

- **AI模块集成**: 新增AI评估器(AIEvaluator)、问答引擎(AIQAEngine)、文本分类器(AITextClassifier)
- **工作流引擎增强**: 支持AI任务类型(AI_EVALUATE、AI_CLASSIFY、AI_QA)
- **AI评估功能**: 评估实际输出与预期输出的匹配程度，包含相似度、正确性、完整性三个维度
- **RAG问答引擎**: 基于知识库回答测试领域问题，支持LLM和fallback两种模式
- **文本分类器**: 自动分类测试结果缺陷类型（逻辑错误、性能、安全、兼容性等）
- **CI/CD增强**: 新增AI测试阶段，更新pre-commit配置添加AI测试检查
- **治理流程AI集成**: 补丁应用后自动评估修复质量

### Fixed

- **策略模式绕过**: 修复转换器注册表查找逻辑，确保策略模式正确应用
- **过期审批记录**: 修复过期审批记录判断逻辑，过期记录强制重新审批
- **审批状态验证**: 添加自动审批记录，确保所有补丁执行前有审批记录
- **测试隔离**: 统一重置单例和模块级实例状态，解决测试间数据污染问题
- **API响应格式**: 统一通过`data`字段访问API响应数据

### Changed

- **CI门禁检查**: 添加`exposed_bugs`目录到排除列表，避免误报
- **覆盖率阈值**: AI模块测试覆盖率要求≥70%
- **日志系统**: 使用logging模块替代print调试语句

### Security

- **登录速率限制**: 通过TokenManager管理登录尝试次数和窗口时间
- **安全扫描集成**: CI流程包含Bandit、pip-audit、Safety安全检查

## [v0.1.0] - Initial Release

### Added

- 基础项目架构搭建
- 治理模块（审批机制、补丁应用、策略模式）
- API层（用户管理、工作流管理）
- 安全模块（认证、授权、安全扫描）
- 基础CI/CD流水线

[v0.2.0]: https://github.com/testai/testai/releases/tag/v0.2.0
[v0.1.0]: https://github.com/testai/testai/releases/tag/v0.1.0