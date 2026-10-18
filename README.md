# OpsAI-IT 故障问答知识库

## 项目简介

`OpsAI-IT 故障问答知识库` 是面向企业内部员工和 IT 运维团队的知识库平台。员工通过钉钉工作台中的“IT 知识库”进入系统，使用知识浏览、分类和搜索解决常见 IT 问题；知识无法解决时，可跳转至现有统一 IT 服务入口。知识库由公司独立部署和管理，钉钉提供统一入口、免登身份和基础集成能力。

## 当前开发基线

- 当前正式开发基线：PRD V1.1A（钉钉集成核心试点版）。
- 历史参考版本：PRD V1.1，不作为当前开发范围的判定依据。
- 当前阶段：Task 12A～12E 历史成果已完成，Task 12 主任务保持 `IN_PROGRESS / codex`；Task 13 六个底层实现提交已存在，但正式状态仍为 `BACKLOG / unassigned`，统一待治理确认与独立验收。
- 本轮治理核验代码基线：`5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e`。GitHub 实时分支 HEAD 与其一致；Gitee 因 SSL 连接错误为 `UNKNOWN`，不得宣称三端同步。

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
- 项目自有 `static/css/opsai.css`；
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
├── static/             项目自有 CSS 与静态资源
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

### 系统角色与本地模拟登录（仅限本地开发）

系统操作角色使用 Django `Group`/`Permission` 实现（与内容受众 `UserGroup` 严格分离），共四类：普通员工、知识编辑员、知识审核员、知识库管理员。

同步系统角色（幂等，可重复执行）：

```powershell
docker compose --env-file .env -f deploy/compose.yaml exec -T web python manage.py sync_system_roles
```

创建本地开发身份（幂等；仅 `DEBUG=True` 且开发登录开关启用时可用，生产配置下拒绝执行）：

```powershell
docker compose --env-file .env -f deploy/compose.yaml exec -T web python manage.py create_dev_users
```

四种本地身份（用户名带 `dev_` 前缀，均为无可用密码、无钉钉身份的安全开发用户）：

| 用户名 | 显示名称 | 系统角色 | staff |
| --- | --- | --- | --- |
| `dev_employee` | 本地模拟-普通员工 | 普通员工 | 否 |
| `dev_editor` | 本地模拟-知识编辑员 | 知识编辑员 | 否 |
| `dev_reviewer` | 本地模拟-知识审核员 | 知识审核员 | 否 |
| `dev_knowledge_admin` | 本地模拟-知识库管理员 | 知识库管理员 | 是（用于访问 Django Admin） |

模拟登录入口：<http://127.0.0.1:8000/dev/login/>（登录/切换身份与登出均只能使用 POST，启用 CSRF；页面只显示当前身份与系统角色）。

开启/关闭：由 `DJANGO_DEV_LOGIN_ENABLED` 环境变量控制，仅本地开发设置读取，**默认关闭**。需要本地模拟登录时，在未跟踪的 `.env` 中显式设置 `DJANGO_DEV_LOGIN_ENABLED=true` 并重启 web 服务；设置 `false`（或删除该变量）即恢复关闭。开关关闭或 `DEBUG=False` 时入口返回 404。

安全边界：本入口仅限本机开发使用，开发用户均无可用密码，不得将该入口作为正式认证方案；生产环境强制关闭模拟登录（production 设置硬编码，环境变量无法重新开启），正式认证后续由钉钉免登实现。

后台权限边界：知识库管理员在 Django Admin 中对用户与系统操作角色 Group 仅保留**只读查看**能力——只有超级管理员（`is_superuser=True`）可以新增、修改、删除用户或系统 Group，非超级管理员即使被直接授予相关内置权限也无法通过后台绕过；账号状态维护与系统角色授权不依赖后台实现，正式功能后续由白名单表单、Service 与审计完成。审核记录在后台对任何人（包括超级管理员）只读，只能由正式审核 Service 在事务中创建；文章版本在版本 Service 落地前对非超级管理员只读；文章的编号、状态、当前/最新版本指针与创建/更新人字段在后台一律只读。

## 文档导航

- [V1.1A 当前开发基线 PRD](docs/02-PRD/产品需求文档PRD-V1.1A-钉钉集成核心试点版-优化稿.md)
- [V1.1 历史参考 PRD](docs/02-PRD/产品需求文档PRD-V1.1-钉钉集成版.md)
- [Django 项目模块目录结构](docs/04-Architecture/Django项目模块目录结构.md)
- [系统架构与 API 接口清单](docs/04-Architecture/系统架构与API接口清单.md)
- [knowledge 候选模型参考代码](docs/05-Database/knowledge_models_reference.py)
- [Codex 分阶段开发指令](docs/06-Process/OpsAI-IT-Codex分阶段开发指令.md)
- [项目变更记录](CHANGELOG.md)

## 开发状态

已正式接入或形成历史验收证据：

- V1.1A 需求与模块化 Django 单体基线；
- accounts、knowledge 核心模型、系统角色、本地模拟登录及后台权限保护；
- 员工首页、分类、正式知识详情和 P0 搜索，服务端受众过滤与拒绝优先；
- Task 12 的 KB 编号、原子 Article 创建、Autosave、Manual Save、版本历史、恢复、管理端编辑和草稿预览；
- Task 12D PostgreSQL 17.11 临时隔离并发补证；
- Task 12E 真实 Chromium 主链、Employee Published-only 隔离及双标签 CAS 验收。

Task 12A～12E 的历史成果保留。Task 12E 为 `DONE / ACCEPTED`，收口 Commit 为 `411535b32db4a40991e3c64228d018e9cebb17ed`；但 Task 12 主任务仍为 `IN_PROGRESS / codex`，正式封板尚缺：

- 项目负责人最终验收；
- `390 × 844` 窄屏视觉验收，或项目负责人明确书面豁免；
- Gitee 当前远端 HEAD 核验；
- 必要治理文件同步。

Task 13 当前正式状态为 `BACKLOG / unassigned`。以下六个提交由负责人决定保留，统一登记为“已有实现、待治理确认与独立验收”，不追认现有资料未证明的历史开工授权：

| Commit | 已有实现 | 历史验证摘要 |
| --- | --- | --- |
| `031a4fca26cebcaf5b67091142ac6b3b82c9cbaa` | Reviewer 空间 Scope、动作权限及审核唯一约束 | `735 passed`、`9 skipped`、`582 subtests` |
| `95af9ca7c06eced103a7a034482959c97df04852` | AuditEvent、Outbox、幂等持久化基础 | `761 passed`、`9 skipped`、`585 subtests` |
| `6d6bb9808ef68b87de63cf1d1762105aa9f8485a` | 提交审核 Service | `785 passed`、`9 skipped`、`624 subtests` |
| `e88bf8e065807343a5b78a0a49c29d0824980b67` | 驳回 Service、审核记录与后继 Draft | `800 passed`、`9 skipped`、`657 subtests` |
| `e422b16ba0826064a629604a217b93978101d5f7` | 原子批准发布与重新发布 | `818 passed`、`9 skipped`、`697 subtests` |
| `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e` | 待审、详情、已审核、提交状态和驳回上下文 Reader | `827 passed`、`9 skipped`、`712 subtests` |

Task 13 尚未完成 PostgreSQL 持久数据兼容预检、并发/锁/事务隔离验收、审核 HTTP/UI、Outbox Worker/通知及负责人独立验收。未跟踪文件 `apps/workflow/tests/test_pg_concurrency.py` 的 SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`，疑似 Task 13-07 验收草稿；来源未确认、未执行、未验收并保持未跟踪。Task 13-07 仅为下一候选技术验收任务，尚未获执行授权，未来只能在一次性隔离 PostgreSQL 环境中按单独合同执行。

当前迁移文件包括 `accounts.0001`～`0002`、`knowledge.0001`～`0006`、`audit.0001` 与 `workflow.0001`。文件存在不代表当前持久数据库已应用；本轮未连接 PostgreSQL、未执行迁移，也未读取真实 `.env`。
