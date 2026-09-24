# OpsAI 项目当前状态

本文档回答“项目现在做到哪里、哪些能力已经正式接入、哪些仍是隔离实验、当前有哪些阻塞和验证证据”。长期项目定位、产品范围和技术路线见 `docs/PROJECT.md`；强制开发规则见根目录 `AGENTS.md`。

## 1. 状态快照

| 项目 | 当前状态 |
| --- | --- |
| 快照日期 | 2026-09-24 |
| 当前工作区 | `D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc` |
| 当前分支 | `fusion/wagtail-poc` |
| 基线 HEAD | `259908f3ffe09c9c444f2add85c4cf00966874bc` |
| 当前阶段 | OpsAI Django 主项目与 Wagtail 的隔离融合验证阶段 |
| 正式技术主体 | Python 3.13 + Django 5.2 LTS 模块化单体 |
| Wagtail 状态 | 融合方向已确认，F02～F08 已形成隔离 PoC 证据，尚未进入正式根依赖、正式 settings 或正式路由 |
| 电脑 B 环境 | Python、正式项目依赖、WSL 2、Docker Desktop、Docker Engine 和 Docker Compose 已恢复；真实 `.env` 尚未配置 |
| 本轮任务 | OPS-H05：建立本状态文档 |

本快照的总体结论是：正式 Django 工程已有账号、知识核心模型、权限基础、健康检查和内容受众过滤等基础能力；Wagtail 核心融合链路已在隔离实验中得到多阶段验证，但尚未完成正式接入、PostgreSQL 验证、生产迁移或正式业务路径切换。不能把 PoC 结果描述为正式上线能力。

## 2. 状态证据规则

当前状态按以下证据优先级维护：

1. 当前分支中的实际代码、配置、迁移和文件；
2. 当前环境中实际执行的测试与检查；
3. Git 历史；
4. 后续建立的任务、状态与交接记录；
5. 历史聊天或口头说明。

文件存在只证明仓库中存在对应实现或声明，不自动证明迁移已应用、服务已启动、持久数据已验证或能力已生产可用。SQLite 内存测试、静态检查和隔离 PoC 也不能替代 PostgreSQL、并发、部署或生产验证。

## 3. 已正式接入的工程基础

### 3.1 Django 工程与运行入口

- 正式配置以 Django 为主体，根 `pyproject.toml` 要求 Python `>=3.13,<3.14`、Django `>=5.2,<5.3`。
- 正式 `INSTALLED_APPS` 包含 `core`、`accounts`、`knowledge`、`search`、`workflow`、`dingtalk`、`service_desk`、`audit` 八个项目 App；未注册 Wagtail。
- 正式根路由已包含 Django Admin、`/health/live`、`/health/ready` 和受开发开关保护的本地模拟登录入口；未挂载 Wagtail 路由。
- 自动测试使用 `config.settings.test` 和 SQLite 内存数据库；该测试结果不代表 PostgreSQL 已验证。

### 3.2 账号、角色与本地开发身份

- `accounts.User`、`Department`、`UserDepartment`、`UserGroup`、`UserGroupMembership` 已存在于正式模型。
- 系统操作角色继续使用 Django `Group` / `Permission`；内容受众使用独立的 `UserGroup`，两者不混用。
- 本地模拟登录仅允许在 `DEBUG=True` 且显式开启 `DJANGO_DEV_LOGIN_ENABLED` 时使用；生产设置硬编码关闭。
- Django Admin 的用户、系统角色、文章生命周期字段、文章版本和审核记录已有相应保护；这些保护不等于完整正式账号治理或内容发布流程已经完成。
- `wagtail-poc` 角色配置档是显式的实验增量入口；相关代码不导入 Wagtail，也不表示 Wagtail 已进入正式配置。

### 3.3 知识核心模型与受众过滤

- `KnowledgeSpace`、`Category`、`Article`、`ArticleVersion`、`ArticleAudience`、`ReviewRecord` 已存在于正式模型。
- 仓库中存在 `accounts.0001`～`0002`、`knowledge.0001`～`0003` 迁移文件；迁移文件存在不代表它们已在当前电脑 B 的持久数据库中应用。
- `apps/knowledge/selectors.py` 已实现 `visible_articles` 和 `can_read_article`，读取语义遵循账号门槛、文章策略与拒绝优先规则。
- 文章后台已具备受控的联合编辑和受众校验能力；Article 编号生成服务尚未实现，正式安全接入前不得绕过编号规则开放新增入口。
- 正式搜索、完整员工详情入口、附件、发布事务、审核事务、审计与 Outbox 闭环尚未全部接入。

### 3.4 容器化开发声明

- `deploy/compose.yaml` 定义 `db` 和 `web` 两个服务。
- PostgreSQL 镜像固定为 `postgres:17.11-alpine3.24`。
- Compose 使用命名卷 `postgres_data`，并要求由未跟踪的真实 `.env` 提供数据库变量。
- 该配置已经过无插值、无 env 解析、无路径解析的结构校验；这只证明 Compose 配置结构可解析，不证明真实变量、镜像、容器、数据卷或数据库可用。

## 4. Wagtail 融合状态与边界

### 4.1 已有隔离 PoC 证据

`experiments/wagtail_f02`～`experiments/wagtail_f08` 已形成分阶段隔离验证，覆盖的主要方向包括：

- Python、Django 与 Wagtail 版本兼容及隔离运行环境；
- 复用现有 `accounts.User` 的认证与 Wagtail 后台准入；
- 候选一对一 `KnowledgeContent` Snippet、Revision 与草稿/正式版本隔离；
- 受控后台编辑、提交、驳回、重提、批准、发布与禁止自审；
- 正式修订快照读取、员工内容受众过滤和实验 HTTP 详情；
- 旧内容迁移演练、正文编码转换、可读文本输出和空正文审核拦截。

这些实验使用合成配置、隔离 runner、SQLite 内存数据库和合成数据。它们提供继续融合的技术证据，但不代表正式 URL、正式模型切换、生产迁移、PostgreSQL、并发、部署或生产安全已经验证。

### 4.2 尚未正式接入

- Wagtail 当前没有进入正式根 `pyproject.toml` 依赖。
- 正式 `config/settings` 没有注册 Wagtail，正式 `config/urls.py` 没有挂载 Wagtail。
- 实验 `KnowledgeContent`、审核发布服务、迁移演练和员工详情仍位于 `experiments/wagtail_*`。
- 旧 `ArticleVersion`、`ReviewRecord` 及业务指针仍须保留；正式切换前不得删除、伪造替代或维护两套独立可编辑的发布状态。
- Wagtail 是否以及何时进入正式根依赖，必须由后续正式融合任务决定；不得为消除测试收集错误而提前加入。

## 5. 电脑 B 开发环境证据

以下结果来自 2026-09-24 在电脑 B 上的实际环境恢复与验证，属于当前机器证据，不自动代表其他电脑或生产环境。

| 检查项 | 当前证据 | 状态 |
| --- | --- | --- |
| Python | Python 3.13.13 x64，安装于 `D:\Software\Python313` | READY |
| 项目虚拟环境 | 仓库根目录 `.venv` 已建立，解释器为 Python 3.13.13 | READY |
| 正式项目依赖 | 已在 `.venv` 中执行 `pip install -e ".[dev]"` | READY |
| 依赖一致性 | `pip check` 输出 `No broken requirements found.` | PASS |
| 正式工程自动测试 | `386 passed` | PASS |
| Django system check | `System check identified no issues (0 silenced).` | PASS |
| Ruff 静态检查 | `All checks passed!` | PASS |
| Ruff 格式检查 | `203 files already formatted` | PASS |
| WSL | WSL 2 已启用并可用 | READY |
| Docker Desktop | 4.92.0，WSL 2 backend | READY |
| Docker Engine | 29.8.0，`docker info` 可正常响应 | READY |
| Docker Compose | v5.5.1 | READY |
| PostgreSQL Compose 声明 | `postgres:17.11-alpine3.24` 已在配置中定义 | READY TO CREATE |
| 真实 `.env` | 不存在，未读取、未创建 | WAITING OWNER |

正式工程测试使用 SQLite 内存测试设置。由于部分设置模块测试会在模块首次导入时检查开发/生产环境变量，电脑 B 的最终 386 项通过记录使用了仅在该测试进程中存在的合成测试变量；变量未写入磁盘、未创建 `.env`、未连接 PostgreSQL，也未访问或修改持久数据。

## 6. 测试范围与 Wagtail 收集边界

### 6.1 正式 Django 工程

电脑 B 已实际执行正式工程范围测试：

```powershell
.\.venv\Scripts\python.exe -m pytest apps tests
```

最终结果为 `386 passed`。同时，Django system check、Ruff 静态检查、Ruff 格式检查和 `pip check` 均通过。因此，当前证据支持“正式 Django 工程测试通过”。

### 6.2 根目录无限定 pytest

在仓库根目录无范围限制执行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

会同时收集 `experiments/wagtail_*`。由于正式根 `pyproject.toml` 环境尚未安装 Wagtail，当前实际结果是在收集阶段出现 Wagtail 导入错误及部分实验包导入错误。

该结果必须按以下边界解释：

- 不能描述为“正式 Django 工程测试失败”；正式工程已有 386 项测试通过。
- 不能把测试收集成功或失败描述为 Wagtail 正式接入证据。
- 不能为消除 PoC 收集错误而擅自把 Wagtail 加入正式项目依赖。
- 后续正式融合任务应决定 Wagtail 根依赖、测试发现边界和实验测试运行入口。

## 7. PostgreSQL 与持久数据状态

电脑 B 当前只完成 Docker 与 Compose 基础环境恢复：

- 真实 `.env` 尚不存在，等待项目负责人后续安全配置。
- 未为 OPS-H05 创建或复制 `.env`。
- 未启动 OpsAI Compose 或 PostgreSQL。
- 未拉取项目 PostgreSQL 镜像。
- 未创建 OpsAI 容器、命名卷或数据库。
- 未执行 `migrate`。
- 未查询、访问或修改任何持久数据库数据。
- 当前电脑 B 的迁移应用状态、数据库注释、PostgreSQL 查询/排序行为和 Wagtail PostgreSQL 行为均未验证。

在负责人安全准备 `.env` 并明确授权数据库操作前，后续 Agent 不得自行填写假密码、启动 PostgreSQL、执行迁移或修改持久数据。

## 8. 尚未完成或尚未正式接入

- Wagtail 正式依赖、正式 settings、正式路由、正式内容模型和统一 Service 接入。
- 旧内容批量迁移、正式切换、失败恢复和回退方案。
- PostgreSQL 下的查询、排序、迁移状态、数据库注释和 Wagtail 行为验证。
- 并发写入、锁策略和冲突处理；现有 `atomic()` 不能单独证明并发安全。
- Article 编号生成服务及完整发布/审核事务。
- 正式员工知识列表、详情、搜索、附件和完整内容生命周期入口。
- 钉钉免登、通讯录同步、工作通知及真实钉钉联调。
- `search`、`workflow`、`dingtalk`、`service_desk`、`audit` 中仍处于骨架或规划状态的业务能力。
- 生产部署、浏览器端到端、容量、性能、备份恢复和上线安全验证。

## 9. 阻塞、风险与技术债

### 9.1 当前阻塞

- 电脑 B 的真实 `.env` 尚未由项目负责人安全准备，因此不能启动本地 PostgreSQL 开发环境或验证真实 Compose 变量。
- Wagtail 正式接入方案和迁移边界尚未由后续融合任务最终确认。

### 9.2 主要风险

- 仓库迁移文件和历史报告不能证明电脑 B 的持久数据库已应用相同迁移。
- Wagtail PoC 使用 SQLite 内存库和合成数据，不能外推为 PostgreSQL 或生产可用。
- 正式员工读取路径、发布事务、审核证据、附件和搜索尚未形成完整端到端闭环。
- 并发、批量数据、失败恢复和正式切换仍缺少实际运行证据。

### 9.3 已知技术债与待决策项

- 正式 `KnowledgeContent` 的 App、表名、字段归属和迁移依赖图。
- 旧 `ArticleVersion` / `ReviewRecord` 的长期历史关联和切换策略。
- Wagtail 根依赖、正式测试发现范围及隔离实验的长期保留方式。
- 正式内容正文结构、旧数据转换和人工复核流程。

## 10. Git 与任务编排状态

- OPS-H05 开始前，分支为 `fusion/wagtail-poc`，HEAD 为 `259908f3ffe09c9c444f2add85c4cf00966874bc`，工作区干净。
- OPS-H05 只允许新增本文件；未修改业务代码、配置、迁移、README、AGENTS 或其他状态/任务文件。
- `docs/HANDOFF.md`、`tasks/TASKS.yaml`、`tasks/CURRENT_TASK.md` 当前仍未建立，不得因本文件存在而推断后续任务已经排期。
- 本轮不创建 Commit，不 Push，不执行 Merge、Rebase、Reset 或 Clean。
- OPS-H05 完成后停止，不自动执行 OPS-H06。

## 11. 下一步边界

下一步必须由项目负责人通过明确任务授权。无论后续任务名称为何，在授权范围未明确前均不得自动执行以下操作：

- 创建或填写真实 `.env`；
- 启动 PostgreSQL 或 OpsAI Compose；
- 执行 `migrate` 或修改持久数据；
- 把 Wagtail 加入正式根依赖、settings 或路由；
- 开始正式模型切换、数据迁移或生产部署；
- 创建任务、交接文件、Commit 或 Push。
