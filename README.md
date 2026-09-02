# OpsAI-IT 故障问答知识库

## 项目简介

`OpsAI-IT 故障问答知识库` 是面向企业内部员工和 IT 运维团队的知识库平台。员工通过钉钉工作台中的“IT 知识库”进入系统，使用知识浏览、分类和搜索解决常见 IT 问题；知识无法解决时，可跳转至现有统一 IT 服务入口。知识库由公司独立部署和管理，钉钉提供统一入口、免登身份和基础集成能力。

## 当前开发基线

- 当前正式开发基线：PRD V1.1A（钉钉集成核心试点版）。
- 历史参考版本：PRD V1.1，不作为当前开发范围的判定依据。
- 当前阶段：**最小 Django 单体项目骨架已初始化，尚未创建正式数据库迁移**。

需求、架构或实现说明发生冲突时，应以 V1.1A PRD 和架构文档为准，并在继续开发前报告冲突。

## 当前范围

- 知识浏览与分类导航；
- 全文搜索、筛选和零结果处理；
- 文章、版本及完整内容生命周期；
- 审核、发布、复审、下架和归档；
- 内容受众权限及服务端权限过滤；
- 钉钉工作台入口、免登和基础集成；
- 统一 IT 服务入口跳转。

## 本期不开发

- 生成式 AI 问答；
- 完整 ITSM 工单系统；
- 微服务；
- Vue 或 React 前后端分离；
- Kubernetes；
- Elasticsearch；
- Redis 和 Celery。

## 技术路线

项目采用**模块化 Django 单体应用**：

- Python 3.13；
- Django 5.2 LTS；
- Django Templates；
- Bootstrap；
- HTMX；
- PostgreSQL；
- Docker Compose；
- Caddy；
- ClamAV（在附件功能阶段接入）。

首版不拆分微服务或独立前端工程。页面渲染、业务逻辑、权限、搜索、审核、钉钉适配和数据库访问均位于同一个 Django 代码库中。

## 目标工程目录

当前已初始化以下核心结构，以架构文档为准：

```text
AI-OpsAI-IT/
├── manage.py
├── config/             Django 项目配置
├── apps/               业务与集成 App
├── templates/          Django Templates 页面
├── static/             Bootstrap、HTMX 和自有静态资源
├── private_media/      私有附件目录
├── tests/              跨 App 测试
├── deploy/             Docker Compose、Caddy 和部署脚本
└── docs/               项目文档唯一入口
```

当前已创建 `manage.py`、分环境 `config/settings`、8 个 App 骨架、模板和静态资源目录，以及最小健康检查测试。`private_media/` 仅作为本地私有附件目录并由 Git 忽略。

## 本地骨架验证

所有 Python 命令均使用项目根目录的 `.venv`：

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe manage.py runserver
```

开发设置暂时指向 SQLite，只用于无迁移的骨架检查；本步骤未运行迁移，也不会创建 `db.sqlite3`。正式本地开发将在后续容器环境阶段切换为 PostgreSQL。

## 文档导航

- [V1.1A 当前开发基线 PRD](docs/02-PRD/产品需求文档PRD-V1.1A-钉钉集成核心试点版-优化稿.md)
- [V1.1 历史参考 PRD](docs/02-PRD/产品需求文档PRD-V1.1-钉钉集成版.md)
- [Django 项目模块目录结构](docs/04-Architecture/Django项目模块目录结构.md)
- [系统架构与 API 接口清单](docs/04-Architecture/系统架构与API接口清单.md)
- [knowledge 候选模型参考代码](docs/05-Database/knowledge_models_reference.py)
- [Codex 分阶段开发指令](docs/06-Process/OpsAI-IT-Codex分阶段开发指令.md)
- [项目变更记录](CHANGELOG.md)

## 开发状态

已完成：

- V1.1A 需求基线；
- Django 模块目录规划；
- 系统架构与 API 清单；
- `knowledge` 候选模型参考代码；
- Codex 分阶段开发计划；
- 项目文档分类归档；
- Django 分环境设置与 8 个 App 骨架；
- 最小自定义用户模型；
- `/health/live` 存活检查及自动化测试。

下一步：在不提前开发业务功能的前提下，准备正式本地 PostgreSQL 运行环境和首批迁移。
