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

## 本地开发环境（Windows + Docker Desktop）

本地开发数据库使用 Docker Compose 提供的 PostgreSQL；Django 既可运行在 Compose 的 `web` 容器中，也可在宿主机 `.venv` 中直接运行（测试环境继续使用 SQLite 内存库）。

### 首次准备

```powershell
# 复制示例配置并替换其中的密钥与密码（必须替换，且 .env 不得提交）
Copy-Item .env.example .env
```

说明：

- `DJANGO_SECRET_KEY` 与 `POSTGRES_PASSWORD` 必须替换为本地随机值；
- 宿主机运行 Django 时使用 `POSTGRES_HOST=localhost`；Compose 的 `web` 服务会自动覆盖为 `POSTGRES_HOST=db`，无需修改 `.env`；
- 所有 Compose 命令均在仓库根目录执行，统一写法为：

```text
docker compose --env-file .env -f deploy/compose.yaml ...
```

### 常用命令

```powershell
# 校验 Compose 配置
docker compose --env-file .env -f deploy/compose.yaml config --quiet

# 拉取数据库镜像并构建 web 镜像
docker compose --env-file .env -f deploy/compose.yaml pull db
docker compose --env-file .env -f deploy/compose.yaml build web

# 启动数据库并等待健康（healthy）
docker compose --env-file .env -f deploy/compose.yaml up -d db
docker compose --env-file .env -f deploy/compose.yaml ps

# 执行迁移（通过一次性 web 容器）
docker compose --env-file .env -f deploy/compose.yaml run --rm web python manage.py migrate

# 启动 web 开发服务
docker compose --env-file .env -f deploy/compose.yaml up -d web

# 查看状态与日志
docker compose --env-file .env -f deploy/compose.yaml ps
docker compose --env-file .env -f deploy/compose.yaml logs -f web db

# 健康检查
curl.exe http://127.0.0.1:8000/health/live
curl.exe http://127.0.0.1:8000/health/ready

# 创建 Django 管理员（交互式）
docker compose --env-file .env -f deploy/compose.yaml run --rm web python manage.py createsuperuser

# 正常停止（保留数据库数据）
docker compose --env-file .env -f deploy/compose.yaml down
```

> ⚠️ **危险操作**：`docker compose --env-file .env -f deploy/compose.yaml down -v` 会**永久删除**本地 PostgreSQL 数据（named volume），仅在明确需要重置数据库时使用。

数据库数据保存在 Docker named volume 中，位于 Docker 的 WSL 2 数据盘（`D:\DockerData\wsl`），与项目目录解耦；`down` 不会删除数据。

如镜像拉取失败，请检查本机网络与 Docker Desktop 的代理设置；本流程不要求登录 Docker Hub。

宿主机直接运行 Django（`db` 容器保持 healthy 时）：

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe -m pytest
```

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
- `/health/live` 存活检查及自动化测试；
- Docker Desktop（WSL 2 后端）与 PostgreSQL 本地开发环境（`deploy/compose.yaml`，db + web）；
- `/health/ready` 就绪检查及自动化测试。

下一步：按 Codex 分阶段开发指令第 6 步接入 `knowledge` 核心数据模型，在此之前不提前开发业务功能。
