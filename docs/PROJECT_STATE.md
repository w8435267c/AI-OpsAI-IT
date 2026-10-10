# OpsAI 项目当前状态

本文档回答“项目现在做到哪里、哪些能力已经正式接入、哪些仍是隔离实验、当前有哪些阻塞和验证证据”。长期项目定位、产品范围和技术路线见 `docs/PROJECT.md`；强制开发规则见根目录 `AGENTS.md`。

## 1. 状态快照

| 项目 | 当前状态 |
| --- | --- |
| 快照日期 | 2026-10-10 |
| 当前工作区 | `D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc` |
| 当前分支 | `fusion/wagtail-poc` |
| 当前业务基线 HEAD | `1e025b9f9a96f7c63207a196dcfd916553940004`（LOCAL / GitHub / Gitee 三端同步） |
| 当前阶段 | Task 12 正式文章创建、草稿与版本保存实施阶段 |
| 正式技术主体 | Python 3.13 + Django 5.2 LTS 模块化单体 |
| Wagtail 状态 | 融合方向已确认，F02～F08 已形成隔离 PoC 证据，尚未进入正式根依赖、正式 settings 或正式路由 |
| 电脑 B 环境 | Python、正式项目依赖、WSL 2、Docker Desktop、Docker Engine 和 Docker Compose 已恢复；根目录 `.env` 存在、被 Git 忽略且未跟踪，内容与适用性未验证 |
| 当前接力元数据任务 | Task 12D 完成后的项目状态与交接元数据同步 |
| 最近完成开发 | Task 12D 版本链与 PostgreSQL 并发补证已 `DONE / SYNCED` |
| 当前开发任务 | Task 12“开发文章创建、草稿和版本保存”，`IN_PROGRESS / codex` |
| Task 10 功能 | PASS |
| Task 10 安全 | PASS |
| Task 10 视觉 | PASS |
| Task 11 Owner Visual Acceptance | PASS |
| Task 11 PostgreSQL 隔离专项 | PASS；PostgreSQL 17.11，临时资源已全部清理 |
| Task 12D PostgreSQL 并发补证 | PASS；PostgreSQL 17.11、临时端口 15432、tmpfs、六类竞争与 Lock wait 均通过，资源已清理；不等同 8J |
| 当前业务主线 | Task 12A～12D 已 `DONE / SYNCED`；Task 12E 为 `NEXT / NOT STARTED` |
| 当前交接状态 | 当前主任务仍为 Task 12；不得提前开始 Task 12E、Task 13 或正式接入 Wagtail |

本快照的总体结论是：Task 10、Task 11 均已正式 `DONE / codex`。Task 12 继续为 `IN_PROGRESS / codex`；Task 12A～12D 已 `DONE / SYNCED`，其中 12D-01 为 `DESIGN PASS`，12D-00、12D-02～12D-06 均为 `DONE / SYNCED`。当前三端同步基线为 `1e025b9f9a96f7c63207a196dcfd916553940004`，下一阶段 Task 12E 仅为 `NEXT / NOT STARTED`。正式内容权威保持 `Article + ArticleVersion`，Task 12 V1 不正式接入 Wagtail；Task 13 保持 `BACKLOG / unassigned`，8J 仍因真实持久 PostgreSQL / `.env` 未核验而保持 `BLOCKED / unassigned`。

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
- 默认自动测试使用 `config.settings.test` 和 SQLite 内存数据库；Task 11 搜索和 Task 12D 版本链另有 PostgreSQL 17.11 仓库外临时隔离专项证据，但均不代表真实持久 PostgreSQL 或生产环境已经验收。

### 3.2 账号、角色与本地开发身份

- `accounts.User`、`Department`、`UserDepartment`、`UserGroup`、`UserGroupMembership` 已存在于正式模型。
- 系统操作角色继续使用 Django `Group` / `Permission`；内容受众使用独立的 `UserGroup`，两者不混用。
- 本地模拟登录仅允许在 `DEBUG=True` 且显式开启 `DJANGO_DEV_LOGIN_ENABLED` 时使用；生产设置硬编码关闭。
- Task 9A 已完成 Django Admin 维护入口与服务端权限边界加固；用户、系统角色、文章生命周期字段、文章版本和审核记录继续受保护。对应 Commit 为 `cab3fc74544ae2199eb64be1e2e7c181269994ba`。
- `wagtail-poc` 角色配置档是显式的实验增量入口；相关代码不导入 Wagtail，也不表示 Wagtail 已进入正式配置。

### 3.3 知识核心模型与受众过滤

- `KnowledgeSpace`、`Category`、`Article`、`ArticleVersion`、`ArticleAudience`、`ReviewRecord` 已存在于正式模型。
- 仓库中存在 `accounts.0001`～`0002`、`knowledge.0001`～`0005` 迁移文件；迁移文件存在不代表它们已在当前电脑 B 的持久数据库中应用。
- `apps/knowledge/selectors.py` 已实现 `visible_articles` 和 `can_read_article`，读取语义遵循账号门槛、文章策略与拒绝优先规则。
- 文章后台已具备受控的联合编辑和受众校验能力；Task 12C 已通过 Service 实现 KB 编号与原子 Article 创建，新增入口不得绕过该正式写入服务。Task 9B-1 当时未创建 Article 样本，并将 Article demo 记为 `N/A - SAFE STOP`。
- Task 9B-1 已新增开发环境专用的幂等最小演示数据命令，使用稳定业务标识创建组织、内容用户组、知识空间和分类样本；一致数据保持不变，冲突数据失败关闭并整体回滚。对应 Commit 为 `9f214d30d6b2934302602bc7a152b27f00274968`。
- 正式员工首页 `/`、分类页 `/categories/<category_id>/`、知识详情页 `/kb/<kb_no>/` 和搜索页 `/search/` 已接入；附件、发布事务、审核事务、审计与 Outbox 闭环尚未接入。
- 员工列表使用 `employee_visible_articles`，详情使用 `get_employee_article_detail`，正式版本来源为 `current_published_version`；Task 10 V1 正文展示使用 `body_plaintext → body_text`，不直接渲染未知 `body` JSON。
- Task 10 V1 正式前端基线为 Django Templates + 项目自有 `static/css/opsai.css`；Bootstrap / HTMX 为 `NOT REQUIRED FOR TASK 10 V1`，后续如有真实需求再以可信固定版本本地接入。
- Task 11A、11B 已完成并双端同步，Task 11 已正式封板为 `DONE / codex`。V1 在 `employee_visible_articles` 返回的当前员工可见正式集合中搜索 `current_published_version.title`、`summary` 和 `body_plaintext`，并实现确定性排序、每页 20 条分页、空查询、零结果、可见结果数量和 KB 详情跳转；草稿、历史版本、全库匹配总数和无权限内容不进入该链路。
- 当前正式模型没有已确认可用的标签或别名字段，Task 11 V1 不实现标签、别名或同义词搜索，也不为其新增 Model / Migration；详情跳转继续使用 `/kb/<kb_no>/` 及 `get_employee_article_detail` 权限链。
- `apps/search` 与 `apps/audit` 当前没有可复用的搜索或点击日志模型。如后续日志需要 `SearchLog`、`ClickLog`、`AuditEvent`、新数据库表或 Migration，必须先提出 `SCOPE QUESTION`；搜索日志不能作为访问授权凭据。
- SQLite 已完成 Task 11 通用功能与安全契约验证；PostgreSQL 17.11 仓库外临时隔离专项进一步确认当前 ORM 查询、中文 substring、特殊字符、权限与状态边界、确定性排序、`NULLS LAST`、count、pagination、查询数量、EXPLAIN/ANALYZE 及 1,000 篇合成数据性能均符合 V1 契约。当前 V1 未使用 PostgreSQL FTS、SearchVector、SearchRank、GIN 或 tsvector；专项结果不替代 8J 的真实持久环境核验。
- Task 12A 已冻结正式写入架构，Task 12B～12D 已按该基线实现并验证：autosave 使用 `expected_lock_version` 乐观 CAS，过期 token 不会 last-write-wins；manual save 将 `DRAFT(n)` 固化为不可变 `SAVED(n)` 并创建新 `DRAFT`；后续版本号在 Article 行锁下按最大值加一；restore 创建带 `restored_from_version` 血缘的新 `DRAFT`，不修改历史来源。Task 12D 不改变 `current_published_version`，员工仍只读取正式 `PUBLISHED` 版本。

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

以下环境事实来自 2026-09-24 在电脑 B 上的实际恢复，Task 10 最终验证与负责人验收证据更新于 2026-10-04；它们属于当前机器证据，不自动代表其他电脑或生产环境。

| 检查项 | 当前证据 | 状态 |
| --- | --- | --- |
| Python | Python 3.13.13 x64，安装于 `D:\Software\Python313` | READY |
| 项目虚拟环境 | 仓库根目录 `.venv` 已建立，解释器为 Python 3.13.13 | READY |
| 正式项目依赖 | 已在 `.venv` 中执行 `pip install -e ".[dev]"` | READY |
| 依赖一致性 | `pip check` 输出 `No broken requirements found.` | PASS |
| 正式工程自动测试 | Task 10 最终回归 `460 passed` | PASS |
| Django system check | `System check identified no issues (0 silenced).` | PASS |
| 迁移一致性检查 | `No changes detected` | PASS |
| Ruff 静态检查 | `All checks passed!` | PASS |
| Ruff 格式检查 | Task 10 范围 `36 files already formatted` | PASS |
| WSL | WSL 2 已启用并可用 | READY |
| Docker Desktop | 4.92.0，WSL 2 backend | READY |
| Docker Engine | 29.8.0，`docker info` 可正常响应 | READY |
| Docker Compose | v5.5.1 | READY |
| PostgreSQL Compose 声明 | `postgres:17.11-alpine3.24` 已在配置中定义 | READY TO CREATE |
| 真实 `.env` | 根目录文件存在，被 Git 忽略且未跟踪；未读取或验证内容、来源、变量完整性及 PostgreSQL 适用性 | BLOCKED / WAITING OWNER |

正式工程测试使用 SQLite 内存测试设置。Task 10 最终 `460 passed` 未写入磁盘配置、未创建或读取真实 `.env`、未连接 PostgreSQL，也未访问或修改持久数据；浏览器验收使用的临时 SQLite、临时脚本和 Django 服务已清理。

## 6. 测试范围与 Wagtail 收集边界

### 6.1 正式 Django 工程

电脑 B 已实际执行正式工程范围测试：

```powershell
.\.venv\Scripts\python.exe -m pytest apps tests
```

Task 10 最终结果为 `460 passed`。页面专项为 `30 passed`，knowledge 为 `310 passed`；Django system check、Ruff 和格式检查通过，迁移一致性检查显示 `No changes detected`。因此，当前证据支持“Task 10 正式 Django 工程验证通过”。

Task 9A 与 Task 9B-1 的实施级结论分别记录在 Commit `cab3fc74544ae2199eb64be1e2e7c181269994ba` 和 `9f214d30d6b2934302602bc7a152b27f00274968`。Article demo 因正式 KB 编号服务尚未实现而按规则记为 `N/A - SAFE STOP`；未创建 Article、ArticleAudience、ArticleVersion 或 ReviewRecord 样本，未通过硬编码、随机值或临时拼接伪造编号。

Task 10 的 10A～10E 分别对应 Commit `cf8bf1ff1692dedd69e5fbf97f0632a460d66c0b`、`9721e2817135a4e6002d9a2d39e151fdc480b8f7`、`8435b4255e459ede018bee2dc6771caf89b6c76e`、`5fb5c1f9cedd6a347e1f240cb41d404b84125dec` 和 `807028ef3d5c2092fa679c811128acd3c07a30fc`，均已完成本地、GitHub、Gitee 三端同步。Desktop `1440 × 900` 与 Mobile `390 × 844` 验收通过；首页在 3 篇和 23 篇时均为 4 queries，分类均为 5 queries，详情为 3 queries，无异常 N+1。项目负责人最终人工确认首页、“电脑故障”分类、KB-900001 正式详情和 Published A 均正常，Draft B、隐藏分类及 KB-900003 无权限内容未泄露，统一 404 文案符合预期；临时 8765 服务、SQLite 数据库和验收目录已安全清理，8000 服务未受影响，正式数据库未操作。

### 6.2 根目录无限定 pytest

在仓库根目录无范围限制执行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

会同时收集 `experiments/wagtail_*`。由于正式根 `pyproject.toml` 环境尚未安装 Wagtail，当前实际结果是在收集阶段出现 Wagtail 导入错误及部分实验包导入错误。

该结果必须按以下边界解释：

- 不能描述为“正式 Django 工程测试失败”；当前正式工程已有 Task 10 `460 passed` 证据。
- 不能把测试收集成功或失败描述为 Wagtail 正式接入证据。
- 不能为消除 PoC 收集错误而擅自把 Wagtail 加入正式项目依赖。
- 后续正式融合任务应决定 Wagtail 根依赖、测试发现边界和实验测试运行入口。

## 7. PostgreSQL 与持久数据状态

电脑 B 当前只完成 Docker 与 Compose 基础环境恢复：

- 仓库根目录 `.env` 当前存在、被 Git 忽略且未跟踪；本项目未读取或验证其内容、来源、变量完整性及 PostgreSQL 适用性。
- 未为 OPS-H05 创建或复制 `.env`。
- 未启动 OpsAI Compose 或 PostgreSQL。
- 未拉取项目 PostgreSQL 镜像。
- 未创建 OpsAI 容器、命名卷或数据库。
- 未执行 `migrate`。
- 未查询、访问或修改任何持久数据库数据。
- 当前电脑 B 的迁移应用状态、数据库注释、PostgreSQL 查询/排序行为和 Wagtail PostgreSQL 行为均未验证。

在项目负责人确认 `.env` 的安全来源和使用范围，并明确授权 PostgreSQL 启动、migration 状态检查、持久数据验证范围及回退边界前，后续 Agent 不得自行填写假密码、启动 PostgreSQL、执行迁移或修改持久数据。

## 8. 尚未完成或尚未正式接入

- Wagtail 正式依赖、正式 settings、正式路由、正式内容模型和统一 Service 接入。
- 旧内容批量迁移、正式切换、失败恢复和回退方案。
- PostgreSQL 下的查询、排序、迁移状态、数据库注释和 Wagtail 行为验证。
- 并发写入、锁策略和冲突处理；现有 `atomic()` 不能单独证明并发安全。
- Article 编号生成服务及完整发布/审核事务。
- 附件、写入与完整内容生命周期入口；员工首页、分类、详情和 P0 搜索入口已完成。
- 钉钉免登、通讯录同步、工作通知及真实钉钉联调。
- `workflow`、`dingtalk`、`service_desk`、`audit` 中仍处于骨架或规划状态的业务能力，以及 `search` 尚未纳入 V1 的标签/别名、高亮和日志能力。
- 生产部署、浏览器端到端、容量、性能、备份恢复和上线安全验证。

## 9. 阻塞、风险与技术债

### 9.1 当前阻塞

- 任务 8J 因根目录 `.env` 的内容、来源、变量完整性及 PostgreSQL 适用性尚未验证，且没有 PostgreSQL 启动、真实 migration 或持久数据访问授权，保持 `BLOCKED / unassigned`；当前不能启动本地 PostgreSQL 开发环境或验证真实 Compose 变量。
- 8J 的阻塞继续影响真实 PostgreSQL 持久环境补充核验，但不影响已使用临时隔离 PostgreSQL 完成并封板的 Task 11；Task 11P-1 PASS 不解除 8J。
- Wagtail 正式接入方案和迁移边界仍待后续正式融合任务决定；Task 10 未改变该边界。

### 9.2 主要风险

- 仓库迁移文件和历史报告不能证明电脑 B 的持久数据库已应用相同迁移。
- Wagtail PoC 使用 SQLite 内存库和合成数据，不能外推为 PostgreSQL 或生产可用。
- 正式员工首页、分类、详情和 P0 搜索读取路径已经形成；Task 12D 的 SQLite 版本链整体验证与 PostgreSQL 17.11 真实并发补证均已通过。发布事务、审核证据和附件尚未形成完整端到端闭环，持久环境和生产容量仍未验证。
- Task 12D 已覆盖六类真实竞争与 Lock wait；更大规模批量数据、生产失败恢复和正式切换仍缺少实际运行证据。

### 9.3 已知技术债与待决策项

- 正式 `KnowledgeContent` 的 App、表名、字段归属和迁移依赖图。
- 旧 `ArticleVersion` / `ReviewRecord` 的长期历史关联和切换策略。
- Wagtail 根依赖、正式测试发现范围及隔离实验的长期保留方式。
- 正式内容正文结构、旧数据转换和人工复核流程。

## 10. Git 与任务编排状态

- OPS-H05 已建立本文件，Commit 为 `e12add28540e9611facb14ca2eee143ebc2f00e3`。
- OPS-H06 已建立 `tasks/TASKS.yaml`，Commit 为 `d512e5791c5dfaacf80a18553babb51953bcc7e3`。
- OPS-H07 已建立 `tasks/CURRENT_TASK.md`，Commit 为 `2c9748fbe0c84ffd42d54a811636429502ee65fb`，并由项目负责人选择任务 9 作为唯一接力业务任务。
- OPS-H08 已建立 `docs/HANDOFF.md`，Commit 为 `78bfda06bf39dc7106529c6c23ad08215087b43c`；OPS-H09 执行前已实时核验本地、GitHub 与 Gitee 三端均为该完整哈希，工作区干净。
- Task 9A 已完成 Django Admin 维护入口和服务端权限边界加固，Commit 为 `cab3fc74544ae2199eb64be1e2e7c181269994ba`。
- Task 9B-1 已完成幂等最小演示数据命令，Commit 为 `9f214d30d6b2934302602bc7a152b27f00274968`。
- Task 9 VERIFY 状态 Commit `c1b32334a7f9d3928d8c6722675accbf553b6b6f` 已完成 GitHub、Gitee 与本地三端同步。
- 2026-09-30，项目负责人完成最终验收并确认 `FINAL ACCEPTANCE: PASS`；Task 9 状态为 `DONE`，负责人为 `codex`，任务 8J 单独保持 `BLOCKED`。
- Task 9 封板后元数据一致性 Commit `91c2e587a3e9c3513a7ed3d9674e69162c04809a` 已完成 GitHub、Gitee 与本地三端同步。
- Task 10 开工状态 Commit `706ece9e5ba3e86e28410ac5e02011d7d9ee266f`、10A～10E 业务 Commit 及 VERIFY 状态 Commit `713bb150d40bcf39cfcaf3be54d6e12a74e68a2e` 已完成双端同步。
- Task 10 的功能、安全、性能、正式工程回归、桌面和手机视觉验收以及项目负责人最终人工验收均已通过，当前状态为 `DONE / codex`。
- 当前无真实 Agent 切换；`docs/HANDOFF.md` 记录当前活动任务、实施基线与下一阶段安全边界。
- Task 11A Commit `6240147054f909c9f88c14d67e99f7c55ccc83d1`、Task 11B Commit `7ac5cd894db052dc3c7eb7e2721dbcc4f34d7ea6` 与 VERIFY 状态归档 Commit `56364d2dbde10d707df8f86aad463e9b1dd3d51c` 已完成双端同步；负责人视觉验收与 Task 11P-1 PostgreSQL 隔离专项均 PASS，Task 11 已正式封板为 `DONE / codex`。
- Task 12A～12D 已完成并双端同步，当前三端同步 HEAD 为 `1e025b9f9a96f7c63207a196dcfd916553940004`。Task 12 当前为 `IN_PROGRESS / codex`；Task 12E 为 `NEXT / NOT STARTED`。Task 13 保持 `BACKLOG / unassigned`，任务 8J 保持 `BLOCKED / unassigned`。
- Task 12D-00 为 `DONE / SYNCED`，12D-01 为 `DESIGN PASS`，12D-02～12D-06 均为 `DONE / SYNCED`；PostgreSQL 17.11 临时并发补证使用端口 15432 与 tmpfs，六类竞争和 Lock wait 均 PASS，资源已完全清理，且不构成 8J 验收。

## 11. 下一步边界

Task 11 已正式 `DONE / codex`。Task 12 继续为 `IN_PROGRESS / codex`，Task 12A～12D 已 `DONE / SYNCED`；下一阶段是 Task 12E，当前仅为 `NEXT / NOT STARTED`。其目标是正式编辑器 UI、草稿编辑入口、autosave / manual save Service 接入、历史版本查看与恢复、草稿预览、员工正式发布内容隔离、视觉 / 人工验收以及 Task 12 最终 closeout，本轮不得开始实施。

当前边界继续禁止自动执行：

- 创建或填写真实 `.env`、读取 `OpsAI.env`；
- 启动 PostgreSQL 或 OpsAI Compose；
- 执行真实 `migrate` 或修改持久数据；
- 把 Wagtail 加入正式根依赖、settings 或路由；
- 创建 Task 11C、修改已完成的 Task 11 业务范围，或在 Task 12E 未授权前实现编辑 UI、预览、审核发布、附件、钉钉或生产部署；
- 创建 Article 假数据或绕过正式编号规则；
- 自行开始 Task 12E、开始 Task 13，或扩大已冻结的 Task 12 V1 范围；
- 未经单独授权创建 Commit 或 Push。
