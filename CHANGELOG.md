# Changelog

本文件记录 AI-OpsAI-IT 项目的重要变更。

格式参考 Keep a Changelog，版本号将在项目发布流程确定后补充。

## [Unreleased]

### Added

- 建立 `docs/01-Research` 至 `docs/09-KnowledgeBase` 的标准文档分类体系。
- 建立 `backend`、`frontend`、`database`、`scripts` 和 `tests` 工程目录骨架。
- 增加项目变更记录文件。
- 增加 V1.1A 钉钉集成核心试点版 PRD。
- 增加 Django 模块化单体项目目录规划。
- 增加系统架构与 API 接口清单。
- 增加 `knowledge` 核心模型参考代码。
- 增加 Codex 分阶段开发指令。
- 增加根目录 `AGENTS.md`，统一后续开发约束。
- 初始化 Django 分环境配置。
- 创建 8 个 App 骨架。
- 增加最小自定义用户模型 `accounts.User`。
- 增加不依赖数据库或外部系统的 `/health/live` 存活检查。
- 增加健康检查自动化测试和 pytest 配置。

### Changed

- 将 `docs` 统一为项目文档唯一入口。
- 将需求调研资料迁移至 `docs/01-Research`。
- 将 Markdown 产品需求文档迁移至 `docs/02-PRD`。
- 更新 README 的项目目标、核心架构、目录说明及维护约定。
- 将 V1.1A 确立为当前正式开发基线，V1.1 保留为历史参考。
- 将项目技术路线调整为 Django 模块化单体。
- 按 PRD、架构、数据库和流程重新归档项目文档。
- 更新 README，反映 Django 尚未初始化的当前开发状态。

### Removed

- 移除根目录重复的 V1.1 PRD 入口；历史版本仍保留在 `docs/02-PRD/`。
- 移除已被正式文件替代的 `.gitkeep` 占位文件。

### Preserved

- 保留全部原始调研资料和 Word 文档。
- 历史 PRD Word 原件继续保存在 `docs/Archive`。

## 2026-08-02

### Added

- 完成第一阶段 Word 到 Markdown 的 PRD 转换。
- 建立初版 `docs` 目录、README 和 Git 忽略规则。
