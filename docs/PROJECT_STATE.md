# OpsAI 项目当前状态

本文档回答“项目现在做到哪里、哪些能力已经正式接入、哪些仍是隔离实验、当前有哪些阻塞和验证证据”。长期项目定位、产品范围和技术路线见 `docs/PROJECT.md`；强制开发规则见根目录 `AGENTS.md`。

## 1. 状态快照

| 项目 | 当前状态 |
| --- | --- |
| 快照日期 | 2026-10-04 |
| 当前工作区 | `D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc` |
| 当前分支 | `fusion/wagtail-poc` |
| 当前业务基线 HEAD | `807028ef3d5c2092fa679c811128acd3c07a30fc` |
| 当前阶段 | OpsAI Django 主项目与 Wagtail 的隔离融合验证阶段 |
| 正式技术主体 | Python 3.13 + Django 5.2 LTS 模块化单体 |
| Wagtail 状态 | 融合方向已确认，F02～F08 已形成隔离 PoC 证据，尚未进入正式根依赖、正式 settings 或正式路由 |
| 电脑 B 环境 | Python、正式项目依赖、WSL 2、Docker Desktop、Docker Engine 和 Docker Compose 已恢复；真实 `.env` 尚未配置 |
| 当前接力元数据任务 | Task 10 `VERIFY → DONE` 正式封板 |
| 最近完成开发 | Task 10 的 10A～10E 均已完成并双端同步 |
| 当前验证任务 | 无；Task 10 已 `DONE / codex`，当前无 `IN_PROGRESS` 或 `VERIFY` 任务 |
| Task 10 功能 | PASS |
| Task 10 安全 | PASS |
| Task 10 视觉 | PASS |
| Owner Visual Acceptance | PASS |
| 下一业务任务 | 等待项目负责人选择；Task 11 未授权开始 |
| 当前交接状态 | 当前无待处理 AI 交接 |

本快照的总体结论是：Task 10 的正式员工首页、受众过滤分类页和 KB 编号知识详情页已经完成；10A～10E 全部同步至 GitHub、Gitee，本地业务基线为 `807028ef3d5c2092fa679c811128acd3c07a30fc`。权限、DENY、草稿和未发布隔离、404 防泄露、缓存、自动转义、桌面与手机响应式以及查询性能均通过验收，正式工程回归为 `460 passed`。项目负责人最终人工视觉验收为 PASS，Task 10 已正式 `DONE / codex`；当前无 `IN_PROGRESS` 或 `VERIFY` 任务，Task 11 仍为 `BACKLOG / unassigned`。Wagtail 核心融合链路仍是隔离实验，8J 仍因真实 PostgreSQL / `.env` 操作未获授权而保持 `BLOCKED`。

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
- Task 9A 已完成 Django Admin 维护入口与服务端权限边界加固；用户、系统角色、文章生命周期字段、文章版本和审核记录继续受保护。对应 Commit 为 `cab3fc74544ae2199eb64be1e2e7c181269994ba`。
- `wagtail-poc` 角色配置档是显式的实验增量入口；相关代码不导入 Wagtail，也不表示 Wagtail 已进入正式配置。

### 3.3 知识核心模型与受众过滤

- `KnowledgeSpace`、`Category`、`Article`、`ArticleVersion`、`ArticleAudience`、`ReviewRecord` 已存在于正式模型。
- 仓库中存在 `accounts.0001`～`0002`、`knowledge.0001`～`0003` 迁移文件；迁移文件存在不代表它们已在当前电脑 B 的持久数据库中应用。
- `apps/knowledge/selectors.py` 已实现 `visible_articles` 和 `can_read_article`，读取语义遵循账号门槛、文章策略与拒绝优先规则。
- 文章后台已具备受控的联合编辑和受众校验能力；Article 编号生成服务尚未实现，正式安全接入前不得绕过编号规则开放新增入口。Task 9B-1 因此未创建 Article 样本，并将 Article demo 记为 `N/A - SAFE STOP`。
- Task 9B-1 已新增开发环境专用的幂等最小演示数据命令，使用稳定业务标识创建组织、内容用户组、知识空间和分类样本；一致数据保持不变，冲突数据失败关闭并整体回滚。对应 Commit 为 `9f214d30d6b2934302602bc7a152b27f00274968`。
- 正式员工首页 `/`、分类页 `/categories/<category_id>/` 和知识详情页 `/kb/<kb_no>/` 已接入；正式搜索、附件、发布事务、审核事务、审计与 Outbox 闭环尚未接入。
- 员工列表使用 `employee_visible_articles`，详情使用 `get_employee_article_detail`，正式版本来源为 `current_published_version`；Task 10 V1 正文展示使用 `body_plaintext → body_text`，不直接渲染未知 `body` JSON。
- Task 10 V1 正式前端基线为 Django Templates + 项目自有 `static/css/opsai.css`；Bootstrap / HTMX 为 `NOT REQUIRED FOR TASK 10 V1`，后续如有真实需求再以可信固定版本本地接入。

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
| 真实 `.env` | 不存在，未读取、未创建 | WAITING OWNER |

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
- 正式搜索、附件、写入与完整内容生命周期入口；员工首页、分类和详情读取入口已完成。
- 钉钉免登、通讯录同步、工作通知及真实钉钉联调。
- `search`、`workflow`、`dingtalk`、`service_desk`、`audit` 中仍处于骨架或规划状态的业务能力。
- 生产部署、浏览器端到端、容量、性能、备份恢复和上线安全验证。

## 9. 阻塞、风险与技术债

### 9.1 当前阻塞

- 任务 8J 因电脑 B 的真实 `.env` 尚未由项目负责人安全准备，且没有数据库操作授权，保持 `BLOCKED`；当前不能启动本地 PostgreSQL 开发环境或验证真实 Compose 变量。
- 8J 的阻塞只影响 PostgreSQL 持久环境补充核验，不影响 Task 10 的最终 `DONE` 状态；Task 10 没有 PostgreSQL、真实 `.env` 或持久数据库前置要求。
- Wagtail 正式接入方案和迁移边界仍待后续正式融合任务决定；Task 10 未改变该边界。

### 9.2 主要风险

- 仓库迁移文件和历史报告不能证明电脑 B 的持久数据库已应用相同迁移。
- Wagtail PoC 使用 SQLite 内存库和合成数据，不能外推为 PostgreSQL 或生产可用。
- 正式员工首页、分类和详情读取路径已经形成；发布事务、审核证据、附件和搜索尚未形成完整端到端闭环。
- 并发、批量数据、失败恢复和正式切换仍缺少实际运行证据。

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
- 当前无真实 Agent 切换，`docs/HANDOFF.md` 保持“当前无待处理 AI 交接”。
- Task 11 及后续业务任务保持 `BACKLOG / unassigned`；任务 8J 保持 `BLOCKED / unassigned`。

## 11. 下一步边界

Task 10 的 10A～10E 已全部完成并双端同步，项目负责人最终人工视觉验收为 PASS，当前状态为 `DONE / codex`。当前没有新的 `IN_PROGRESS` 或 `VERIFY` 任务；下一任务等待项目负责人正式指定，Task 11 保持 `BACKLOG / unassigned`，不得自行启动。

当前边界继续禁止自动执行：

- 创建或填写真实 `.env`、读取 `OpsAI.env`；
- 启动 PostgreSQL 或 OpsAI Compose；
- 执行真实 `migrate` 或修改持久数据；
- 把 Wagtail 加入正式根依赖、settings 或路由；
- 实现 Article 创建、KB 编号、P0 搜索、审核发布、附件、钉钉或生产部署；
- 创建 Article 假数据或绕过正式编号规则；
- 提前启动 Task 11 或其他后续任务；
- 未经单独授权创建 Commit 或 Push。
