# OpsAI 项目当前状态

本文档回答“项目现在做到哪里、哪些能力已经正式接入、哪些仍是隔离实验、当前有哪些阻塞和验证证据”。长期项目定位、产品范围和技术路线见 `docs/PROJECT.md`；强制开发规则见根目录 `AGENTS.md`。

## 1. 状态快照

| 项目 | 当前状态 |
| --- | --- |
| 快照日期 | 2026-10-31 |
| 当前工作区 | `D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc` |
| 当前分支 | `fusion/wagtail-poc` |
| 本轮实施授权基线 HEAD | `176131758efa01658ffe3a9fee5dee517937154a` |
| 远端实时核验 | 最近一次实时证据：GitHub `fusion/wagtail-poc` 为 `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e`，本地基线纯领先 11 个提交；Gitee 因 SSL 连接失败为 `UNKNOWN`；本轮禁止 Push |
| 当前阶段 | LOCAL-DEMO-REVIEW-WEB-01 已完成离线 Web 实现与自动化验收；独立演示浏览器验收待环境恢复 |
| 正式技术主体 | Python 3.13 + Django 5.2 LTS 模块化单体 |
| Wagtail 状态 | 融合方向已确认，F02～F08 已形成隔离 PoC 证据，尚未进入正式根依赖、正式 settings 或正式路由 |
| 电脑 B 环境 | Python、正式项目依赖、WSL 2、Docker Desktop、Docker Engine 和 Docker Compose 已恢复；根目录 `.env` 存在、被 Git 忽略且未跟踪，内容与适用性未验证 |
| 最近完成开发 | `LOCAL-DEMO-REVIEW-WEB-01`，`DONE / OFFLINE WEB IMPLEMENTATION COMPLETED` |
| 当前开发任务 | 无；后续必须基于新的完整 HEAD 单独授权 |
| Task 10 功能 | PASS |
| Task 10 安全 | PASS |
| Task 10 视觉 | PASS |
| Task 11 Owner Visual Acceptance | PASS |
| Task 11 PostgreSQL 隔离专项 | PASS；PostgreSQL 17.11，临时资源已全部清理 |
| Task 12D PostgreSQL 并发补证 | PASS；PostgreSQL 17.11、临时端口 15432、tmpfs、六类竞争与 Lock wait 均通过，资源已清理；不等同 8J |
| Task 12E 真实浏览器验收 | `PASS_WITH_VISUAL_FINDINGS`；P0/P1/P2 均为 0，P3 为 2 |
| 当前业务主线 | 本地演示数据、Service 闭环和审核 Web 已实现；`TASK13-REVIEW-WEB-E2E-01` 的独立 PostgreSQL 与桌面/手机浏览器验收已 PASS；Task 12 暂停且主任务尚未正式封板，Task 13 主任务仍为 BACKLOG |
| Task 13 代码现状 | 六个既有提交保留；Task 13-08 核心修复 Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 已完成并有修正夹具 PostgreSQL 14 PASS 证据，Task 13 主任务仍未完成 |
| 当前交接状态 | 无真实 Agent 切换；审核 Web E2E 切片已 `DONE / PASS`；Task 12 为 `PAUSED / IN_PROGRESS HISTORY PRESERVED`；Task 13 主任务为 `BACKLOG / unassigned` |

本快照的总体结论是：Task 10、Task 11 均已正式 `DONE / codex`；Task 12A～12E 的历史成果保留，但 Task 12 主任务暂停且未封板。DATA-01 已在独立本地演示环境中证明正式 Service 的创建、保存、提交、独立审核、发布、员工搜索与详情链路可运行，不能外推为生产上线。`TASK13-REVIEW-WEB-E2E-01` 已补足审核 HTTP/UI 的独立 E2E、PostgreSQL 与浏览器证据；Task 13 主任务仍缺 Worker/通知、原持久环境前置检查和主任务级负责人验收，继续为 `BACKLOG / unassigned`。正式内容权威保持 `Article + ArticleVersion`，8J 仍为 `BLOCKED / unassigned`。

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
- 仓库中存在 `accounts.0001`～`0002`、`knowledge.0001`～`0006`、`audit.0001` 与 `workflow.0001` 迁移文件；迁移文件存在不代表它们已在当前电脑 B 的持久数据库中应用。
- `apps/knowledge/selectors.py` 已实现 `visible_articles` 和 `can_read_article`，读取语义遵循账号门槛、文章策略与拒绝优先规则。
- 文章后台已具备受控的联合编辑和受众校验能力；Task 12C 已通过 Service 实现 KB 编号与原子 Article 创建，新增入口不得绕过该正式写入服务。Task 9B-1 当时未创建 Article 样本，并将 Article demo 记为 `N/A - SAFE STOP`。
- Task 9B-1 已新增开发环境专用的幂等最小演示数据命令，使用稳定业务标识创建组织、内容用户组、知识空间和分类样本；一致数据保持不变，冲突数据失败关闭并整体回滚。对应 Commit 为 `9f214d30d6b2934302602bc7a152b27f00274968`。
- 正式员工首页 `/`、分类页 `/categories/<category_id>/`、知识详情页 `/kb/<kb_no>/` 和搜索页 `/search/` 已接入。Task 13 已存在 Service 层提交、驳回、原子批准发布、审核 Reader、AuditEvent、Outbox 与幂等基础；`TASK13-REVIEW-WEB-E2E-01` 已验证审核 HTTP/UI、隔离 PostgreSQL 并发/幂等回归与浏览器链路。Outbox Worker/通知和完整生产入口仍未实现；附件仍未接入。
- 员工列表使用 `employee_visible_articles`，详情使用 `get_employee_article_detail`，正式版本来源为 `current_published_version`；Task 10 V1 正文展示使用 `body_plaintext → body_text`，不直接渲染未知 `body` JSON。
- Task 10 V1 正式前端基线为 Django Templates + 项目自有 `static/css/opsai.css`；Bootstrap / HTMX 为 `NOT REQUIRED FOR TASK 10 V1`，后续如有真实需求再以可信固定版本本地接入。
- Task 11A、11B 已完成并双端同步，Task 11 已正式封板为 `DONE / codex`。V1 在 `employee_visible_articles` 返回的当前员工可见正式集合中搜索 `current_published_version.title`、`summary` 和 `body_plaintext`，并实现确定性排序、每页 20 条分页、空查询、零结果、可见结果数量和 KB 详情跳转；草稿、历史版本、全库匹配总数和无权限内容不进入该链路。
- 当前正式模型没有已确认可用的标签或别名字段，Task 11 V1 不实现标签、别名或同义词搜索，也不为其新增 Model / Migration；详情跳转继续使用 `/kb/<kb_no>/` 及 `get_employee_article_detail` 权限链。
- `apps/search` 当前没有可复用的搜索或点击日志模型；`apps/audit` 已存在 Task 13 的 `AuditEvent` 基础，但不等同于搜索/点击日志或完整审计运维能力。搜索日志不能作为访问授权凭据。
- SQLite 已完成 Task 11 通用功能与安全契约验证；PostgreSQL 17.11 仓库外临时隔离专项进一步确认当前 ORM 查询、中文 substring、特殊字符、权限与状态边界、确定性排序、`NULLS LAST`、count、pagination、查询数量、EXPLAIN/ANALYZE 及 1,000 篇合成数据性能均符合 V1 契约。当前 V1 未使用 PostgreSQL FTS、SearchVector、SearchRank、GIN 或 tsvector；专项结果不替代 8J 的真实持久环境核验。
- Task 12A 已冻结正式写入架构，Task 12B～12D 已按该基线实现并验证：autosave 使用 `expected_lock_version` 乐观 CAS，过期 token 不会 last-write-wins；manual save 将 `DRAFT(n)` 固化为不可变 `SAVED(n)` 并创建新 `DRAFT`；后续版本号在 Article 行锁下按最大值加一；restore 创建带 `restored_from_version` 血缘的新 `DRAFT`，不修改历史来源。Task 12D 不改变 `current_published_version`，员工仍只读取正式 `PUBLISHED` 版本。
- Task 12E 已完成管理端知识列表、新建 Article、Draft 编辑器、Autosave、Manual Save、History、History Detail、Restore 与 Draft Preview，并保持 Employee Published-only 隔离。Task 12E-09A 使用仓库外独立 SQLite 与真实 Chromium 完成主链、权限隔离和双标签 CAS 验收，结论为 `PASS_WITH_VISUAL_FINDINGS`；详细证据见 `docs/06-Process/Task12E-管理端知识编辑链验收.md`。
- Task 13 的六个既有提交依次实现 Reviewer 空间授权与约束、Audit/Outbox/幂等底座、提交审核、驳回、原子批准发布和审核 Reader；这些是当前代码事实，不代表历史授权或正式验收已补齐。

### 3.4 容器化开发声明

- `deploy/compose.yaml` 定义 `db` 和 `web` 两个服务。
- PostgreSQL 镜像固定为 `postgres:17.11-alpine3.24`。
- Compose 使用命名卷 `postgres_data`，并要求由未跟踪的真实 `.env` 提供数据库变量。
- 该配置已经过无插值、无 env 解析、无路径解析的结构校验；这只证明 Compose 配置结构可解析，不证明真实变量、镜像、容器、数据卷或数据库可用。

### 3.5 LOCAL-DEMO-DATA-01 独立演示能力

- 实现 Commit `d184033ee06630c1b1e23081c8060eb12848f4dd` 只新增 `deploy/compose.local-demo.yaml`、演示配置样例、演示初始化命令、对应测试和操作 SOP 五个文件。
- `opsai-local-demo` 使用独立 Project、8001 端口、PostgreSQL 数据卷、媒体卷、网络和仓库外配置；实施证据显示原 `opsai-it` 容器、原数据卷、原数据库、原账号与迁移前备份未被修改。
- 演示初始化通过正式 Service 完成文章创建、手动保存、提交审核和独立审核员批准发布；重复执行保持幂等，外部通知发送次数为 0。
- 自动证据为专项 `10 passed`，正式 `apps/tests` 回归 `837 passed`、`23 skipped`、`712 subtests`；Ruff、格式、Python 编译、Compose 解析、Django check 与差异检查通过。
- 实际运行证据包括 live/ready 200、员工首页、搜索、正式详情、未登录和无权隔离的浏览器验收，以及演示数据库备份恢复成功。
- 这是一套本地隔离演示能力，不是生产上线。审核 Web 页面现已实现，但本轮无法启动 Docker Engine，独立演示环境浏览器验收仍为 `NOT TESTED`。

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
| 正式工程自动测试 | DATA-01 实现提交记录：`apps/tests` 为 `837 passed`、`23 skipped`、`712 subtests`；本轮文档治理未重跑业务测试 | HISTORICAL PASS |
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

正式工程测试使用 SQLite test settings。Task 12E 累计正式自动化证据为 `717 passed`、`9 skipped`、`571 subtests`、`0 failed`；Task 13 六个提交逐步记录至 `827 passed`、`9 skipped`、`712 subtests`、`0 failed`；DATA-01 实现提交进一步记录 `apps/tests` 为 `837 passed`、`23 skipped`、`712 subtests`。这些均是对应历史提交证据，本轮文档治理不重跑业务测试。DATA-01 的独立 PostgreSQL 演示与备份恢复证据只适用于 `opsai-local-demo`，不解除 8J 的原持久环境阻塞。

## 6. 测试范围与 Wagtail 收集边界

### 6.1 正式 Django 工程

电脑 B 已执行正式工程范围测试：

```powershell
.\.venv\Scripts\python.exe -m pytest apps tests
```

Task 12E-08 及此前阶段累计形成的最终证据为 `717 passed`、`9 skipped`、`571 subtests`、`0 failed`。Django system check、`makemigrations --check --dry-run`、Ruff、Format、`git diff --check` 与 `node --check` 均通过。该结果不是 Task 12E-09A 重新执行；Task 12E-09A 单独提供真实 Chromium 页面验收证据。

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

电脑 B 的原 `opsai-it` 环境与 DATA-01 隔离演示环境必须分开解释：

- 仓库根目录 `.env` 当前存在、被 Git 忽略且未跟踪；本项目未读取或验证其内容、来源、变量完整性及 PostgreSQL 适用性。
- 未为 OPS-H05 创建或复制 `.env`。
- 原 `opsai-it` 环境的根 `.env` 安全来源和适用性仍未纳入 8J 验收；DATA-01 没有把演示配置或结论写回原环境。
- `opsai-local-demo` 已在独立数据库执行迁移、创建演示数据并完成备份恢复；这些写入受 DATA-01 授权且仅属于隔离演示资源。
- DATA-01 不证明原持久数据库、生产数据库、数据库注释、生产容量或 Wagtail PostgreSQL 行为已通过验收。

在项目负责人确认 `.env` 的安全来源和使用范围，并明确授权 PostgreSQL 启动、migration 状态检查、持久数据验证范围及回退边界前，后续 Agent 不得自行填写假密码、启动 PostgreSQL、执行迁移或修改持久数据。

## 8. 尚未完成或尚未正式接入

- Wagtail 正式依赖、正式 settings、正式路由、正式内容模型和统一 Service 接入。
- 旧内容批量迁移、正式切换、失败恢复和回退方案。
- PostgreSQL 下的查询、排序、迁移状态、数据库注释和 Wagtail 行为验证。
- 并发写入、锁策略和冲突处理；现有 `atomic()` 不能单独证明并发安全。
- Task 13 的 Outbox Worker/通知发送、原持久数据库迁移前置检查及负责人对完整主任务范围的独立整体验收。Service、Reader、审核 HTTP/UI、Task 13-08 行锁核心修复及 DATA-01/E2E 的隔离验收已存在，不得再描述为“尚未开始”。
- PG07 正式测试归档已完成，不再属于未完成项；Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 仅新增该测试文件，已归档 SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`。
- 附件与完整生产审核发布生命周期；审核 Web 已完成独立 E2E 验收，但不等同生产上线。员工首页、分类、详情、P0 搜索、Task 12E 管理端知识编辑链和 DATA-01 隔离演示服务链已完成。
- `DINGTALK-H5-SSO-MVP-01` 已登记但未开始：钉钉 H5 免登、员工身份映射和既有受众权限复用属于其拟议最小范围；通讯录同步、工作通知及真实钉钉联调仍未开发。
- `workflow` 已有 Task 13 Service/Reader/Outbox/幂等基础，`audit` 已有 AuditEvent 基础；两者的完整 HTTP/UI、Worker 与运行闭环仍未形成。`dingtalk`、`service_desk` 仍主要处于骨架或规划状态，`search` 的标签/别名、高亮和日志能力尚未纳入 V1。
- 生产部署、移动端 Task 12E 视觉验收、正式持久 PostgreSQL、容量和上线安全验证；DATA-01 的演示备份恢复不能替代生产备份恢复。

## 9. 阻塞、风险与技术债

### 9.1 当前阻塞

- 任务 8J 因根目录 `.env` 的内容、来源、变量完整性及 PostgreSQL 适用性尚未验证，且没有 PostgreSQL 启动、真实 migration 或持久数据访问授权，保持 `BLOCKED / unassigned`；当前不能启动本地 PostgreSQL 开发环境或验证真实 Compose 变量。
- 8J 的阻塞继续影响真实 PostgreSQL 持久环境补充核验，但不影响已使用临时隔离 PostgreSQL 完成并封板的 Task 11；Task 11P-1 PASS 不解除 8J。
- Wagtail 正式接入方案和迁移边界仍待后续正式融合任务决定；Task 10 未改变该边界。

### 9.2 主要风险

- 仓库迁移文件和历史报告不能证明电脑 B 的持久数据库已应用相同迁移。
- Wagtail PoC 使用 SQLite 内存库和合成数据，不能外推为 PostgreSQL 或生产可用。
- 正式员工首页、分类、详情、P0 搜索读取路径和 Task 12E 管理端知识编辑链已经形成；DATA-01 又在独立演示环境中完成了一篇文章的 Service 审核发布、员工搜索/详情、权限隔离和备份恢复。Task 13 已有发布事务、审核证据、Reader 与审核 Web，Task 13-08-002 的修正夹具隔离并发 14 项通过，且 `TASK13-REVIEW-WEB-E2E-01` 已运行 114 项隔离 PostgreSQL 回归与浏览器验收；但 Worker/通知、原持久环境和完整主任务验收仍未形成生产闭环，Task 12E 窄屏视觉、附件和生产容量仍未验证。
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
- Task 12E-02～12E-08 分别对应 Commit `eababf6f19043fe44a925bd86e3142f38c80805a`、`b239e0186ae999e99fa3c51e18965d6a56eee4b9`、`a49bbf5fadea6c17ad2429adbbb149816d23240d`、`9c514983698a9e3edcfe76af129ffe2eb543cd75`、`a8238954d3f7639bdb9b0eb6f494eede2b7c317b`、`4b565784dbcbb8f0d9aa005797cf3cac1668f7b1` 和 `4e4a0bd25abed587c587c8bfc419b3ebe583198d`；历史记录显示这些提交当时已完成三端同步，但不替代本轮 Gitee 当前远端核验。
- Task 12E-09A 真实 Chromium 验收为 `PASS_WITH_VISUAL_FINDINGS`：Manage → Create → Edit → Autosave → Manual Save → History → Restore → Preview 主链、Employee Published-only 隔离和双标签 CAS 冲突均 PASS；P0/P1/P2 为 0，P3 为 2。Task 12E 当前为 `DONE / ACCEPTED`。
- Task 12E-09B 收口 Commit 为 `411535b32db4a40991e3c64228d018e9cebb17ed`；其父提交为 `4e4a0bd25abed587c587c8bfc419b3ebe583198d`，仅更新验收与治理文档。
- Task 13 六个线性提交为 `031a4fca26cebcaf5b67091142ac6b3b82c9cbaa`、`95af9ca7c06eced103a7a034482959c97df04852`、`6d6bb9808ef68b87de63cf1d1762105aa9f8485a`、`e88bf8e065807343a5b78a0a49c29d0824980b67`、`e422b16ba0826064a629604a217b93978101d5f7`、`5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e`。负责人决定保留，但统一按已有实现、待治理确认与独立验收登记，不追认现有资料未证明的历史开工授权。
- Task 13-08 核心修复 Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 只修改 `apps/workflow/services.py` 及 Submit/Reject 两个测试文件；提交内 RED 2 项、GREEN 2 项及 199 项唯一回归通过。
- Task 13-08-001 为 PostgreSQL 13 PASS、1 FAIL；Task 13-08-002 的修正夹具为 14 PASS、0 FAIL。二者均为保留的隔离 Evidence；正式归档由后续单文件 Commit 独立完成，不得把归档描述成重新运行 PostgreSQL。
- Task 13-08-ARCHIVE Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 的父提交为 `8049e17eabf97148b42a6c6b0196ac098bf1613c`，只新增 `apps/workflow/tests/test_pg_concurrency.py`；SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`，Git 提交统计为新增 993 行。Python 编译、Ruff lint、format check 和 Git 检查通过，归档时没有重新执行 PostgreSQL；原始版本已在独立 Evidence 目录备份。
- LOCAL-DEMO-G01 治理 Commit 为 `60408cdda7a281066eb1cd043e91ff13a2d7e005`；G02 治理 Commit 为 `04d9cea907d3b35e143a3475568aa05291115243`；DATA-01 实现 Commit 为 `d184033ee06630c1b1e23081c8060eb12848f4dd`。
- DATA-01 实现提交只新增五个授权文件；专项 10 PASS、正式 `apps/tests` 837 PASS、浏览器验收和备份恢复证据均已写入提交及 SOP。
- 最近一次实时远端核验中，GitHub `fusion/wagtail-poc` 为 `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e`，本地 DATA-01 基线相对其纯领先 11 个提交；Gitee 因 SSL 连接失败为 `UNKNOWN`。本状态不宣称三端同步，G03 不执行 Push。
- Task 12 当前保持 `PAUSED / IN_PROGRESS HISTORY PRESERVED`；Task 13 主任务保持 `BACKLOG / unassigned`，其 `TASK13-REVIEW-WEB-E2E-01` 子任务为 `DONE / PASS`；任务 8J 保持 `BLOCKED / unassigned`。
- `LOCAL-DEMO-REVIEW-WEB-01` 已完成离线实现：审核队列、详情、本人已审核记录、提交、批准与驳回页面均复用既有 Reader/Service；专项与关联测试 `51 passed`、`118 subtests`，全量离线回归 `846 passed`、`23 skipped`、`712 subtests`。
- Task 12D-00 为 `DONE / SYNCED`，12D-01 为 `DESIGN PASS`，12D-02～12D-06 均为 `DONE / SYNCED`；PostgreSQL 17.11 临时并发补证使用端口 15432 与 tmpfs，六类竞争和 Lock wait 均 PASS，资源已完全清理，且不构成 8J 验收。

## 11. 下一步边界

DATA-01 与审核 Web 离线实现均已完成；`TASK13-REVIEW-WEB-E2E-01` 已在独立环境完成审核页面的桌面和 `390 × 844` 浏览器验收以及 PostgreSQL 定向回归。`DINGTALK-H5-SSO-MVP-01` 已登记为唯一下一项业务任务，但没有代码实施、真实钉钉调用或凭据访问授权。Task 12 继续暂停，只有在负责人最终验收、`390 × 844` 窄屏视觉验收或书面豁免、Gitee 当前远端 HEAD 核验及必要治理同步完成后，才具备申请正式封板的条件。Task 13 六个既有提交保留，主任务正式状态仍为 `BACKLOG / unassigned`；本 E2E 子任务不代表 Task 13 全面开工或完成。

当前边界继续禁止自动执行：

- 创建或填写真实 `.env`、读取 `OpsAI.env`；
- 启动 PostgreSQL 或 OpsAI Compose；
- 执行真实 `migrate` 或修改持久数据；
- 把 Wagtail 加入正式根依赖、settings 或路由；
- 创建 Task 11C、修改已完成的 Task 11 / Task 12E / DATA-01 业务范围，或未经逐文件实施授权实现后续审核功能、附件、钉钉或生产部署；
- 创建 Article 假数据或绕过正式编号规则；
- 继续开发 Task 13、自动重做 DATA-01、Task 13-08 或审核 Web、自动恢复 Task 13-07、重复归档 `apps/workflow/tests/test_pg_concurrency.py`、执行 P3-UI-02 或扩大已冻结的 Task 12 V1 范围；
- 未经单独授权创建 Commit 或 Push。
