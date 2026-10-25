# OpsAI Current Task

> 当前业务主任务仍为 Task 12“开发文章创建、草稿和版本保存”，状态为 `IN_PROGRESS / codex`。Task 13-08 核心修复与 Task 13-08-ARCHIVE 单文件归档均已登记为 `DONE / unassigned`；Task 12E 保持 `DONE / ACCEPTED`，Task 13 主任务保持 `BACKLOG / unassigned`。P3-UI-02 仅是下一项试点候选，尚未获得独立执行授权。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `Task 12` |
| 任务名称 | 开发文章创建、草稿和版本保存 |
| 优先级 | `MUST` |
| 当前状态 | `IN_PROGRESS / codex`；Task 12A～12E 已完成，仍待主任务最终封板条件 |
| 当前负责人 | `codex` |
| 治理登记日期 | `2026-10-25` |
| 局部例外 | Task 13-08 核心修复与 Task 13-08-ARCHIVE 归档已完成；二者不代表 Task 13 全面开工或完成 |
| 当前分支 | `fusion/wagtail-poc` |
| 本轮治理起始 HEAD | `a066b8e158d53770b2f9dab5e2c7e70c87817975` |
| PG07 归档证据 | Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 仅新增 `apps/workflow/tests/test_pg_concurrency.py`；父提交为 `8049e17eabf97148b42a6c6b0196ac098bf1613c` |
| 正式任务状态 | Task 12 为 `IN_PROGRESS / codex`；Task 13 为 `BACKLOG / unassigned` |
| 已完成核心修复 | Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 从 Submit/Reject 的 Article 加锁查询中移除可空 `current_published_version` 联表，只保留 `space` |
| 已归档 PG07 | `apps/workflow/tests/test_pg_concurrency.py` 已纳入 Git；SHA-256 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`，Git 提交统计新增 993 行 |
| 历史原始版本 | 归档前原始文件 SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`，已在独立 Evidence 目录备份 |
| P3-UI-02 | 下一项试点候选；不是 `READY`，不是当前任务，未获执行授权 |
| 当前允许动作 | 仅完成本次五份治理文档状态收口及一个本地治理 Commit；不得开始 P3-UI-02 或其他业务开发。 |

## 2. 已完成阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 12A | 正式写入契约与融合范围冻结 | `DONE / SYNCED` |
| 12B | 最小 Model / Migration 增量 | `DONE / SYNCED` |
| 12C | KB 编号服务与原子 Article 创建 | `DONE / SYNCED` |
| 12D | autosave、manual save、版本链与历史恢复 | `DONE / SYNCED` |
| 12D-00 | SAVED `full_clean` 与数据库约束一致性修复 | `DONE / SYNCED` |
| 12D-01 | 版本写入状态机、乐观锁与历史恢复设计审计 | `DESIGN PASS` |
| 12D-02 | autosave CAS 与公共版本写入合同 | `DONE / SYNCED` |
| 12D-03 | manual save、`version_no` 与历史不可变收口 | `DONE / SYNCED` |
| 12D-04 | history restore 与管理侧版本历史 Reader | `DONE / SYNCED` |
| 12D-05 | 版本链综合 SQLite 收口验证 | `DONE / SYNCED` |
| 12D-06 | PostgreSQL 真实并发补证 | `DONE / SYNCED` |
| 12E | 正式管理编辑页面、草稿预览与浏览器验收 | `DONE / ACCEPTED` |
| 12E-02～12E-08 | 管理列表、Create、Draft 编辑、Autosave、Manual Save、History/Restore、Draft Preview | `DONE / SYNCED` |
| 12E-09A | 真实 Chromium 完整管理链与视觉验收 | `PASS_WITH_VISUAL_FINDINGS` |
| 12E-09B | Task 12E 验收文档与状态收口，Commit `411535b32db4a40991e3c64228d018e9cebb17ed` | `DONE` |
| 13-08 | PostgreSQL 可空关联行锁最小修复，Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` | `DONE` |
| 13-08-001 | 原始 PG07 夹具 PostgreSQL 复验：13 PASS、1 FAIL | `FAILED / EVIDENCE PRESERVED` |
| 13-08-002 | 修正 PG07 夹具 PostgreSQL 复验：14 PASS、0 FAIL | `PASS / EVIDENCE PRESERVED` |
| 13-08-ARCHIVE | PG07 已验证修正夹具单文件归档，Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` | `DONE` |

## 3. Task 12D 交接摘要

- autosave 使用 `expected_lock_version` 做乐观 CAS；过期 token 明确冲突，不采用 last-write-wins。
- manual save 将 `DRAFT(n)` 固化为不可变 `SAVED(n)`，并创建新的工作 `DRAFT`。
- 后续 `version_no` 在 Article 行锁保护下按现有最大版本号加一生成。
- 正式 Writer 与 Admin 均不能修改 `SAVED` 历史。
- restore 不修改来源历史，而是创建新 `DRAFT`；`restored_from_version` 保留恢复血缘。
- Task 12D 不改变 `current_published_version`；员工读取仍只使用正式 `PUBLISHED` 版本。
- SQLite 版本链整体验证通过；PostgreSQL 17.11 真实并发验证通过。

## 4. PostgreSQL 证据边界

Task 12D-06 在 PostgreSQL 17.11 仓库外临时隔离环境完成验证：端口 `15432`、存储为 `tmpfs`，六类真实竞争与 Lock wait 均为 PASS，临时验证资源已完全清理。

该证据不等于 8J 的真实持久 PostgreSQL 验证，不证明正式数据库或生产环境已经验收。真实 `.env` 的内容、来源、完整性和适用性仍未验证；8J 继续为 `BLOCKED / unassigned`。

## 5. Task 12E 完成与验收摘要

Task 12E 已完成以下范围：

1. 正式编辑器 UI 与草稿编辑入口；
2. 接入 autosave / manual save Service；
3. 历史版本查看与恢复入口；
4. 草稿预览；
5. 保持员工正式发布内容隔离；
6. 完成真实 Chromium 管理主链、Employee 隔离与双标签 CAS 验收。

Task 12E 累计自动化证据为 `717 passed`、`9 skipped`、`571 subtests`、`0 failed`；Django check、迁移一致性、Ruff、Format、`git diff --check` 与 `node --check` 均 PASS。Task 12E-09A 真实浏览器结论为 `PASS_WITH_VISUAL_FINDINGS`，P0/P1/P2 均为 0，P3 为 2。详细证据见 `docs/06-Process/Task12E-管理端知识编辑链验收.md`。

两项 P3 分别为 Create 表单视觉一致性和 Edit 页“预览草稿”/“保存版本并继续编辑”操作层级，均为 `BACKLOG / non-blocking`，本轮不修复。窄屏验收为 `NOT_EXECUTED_BROWSER_CAPABILITY`，不得宣称移动端视觉 PASS。

Task 12E 已 `DONE / ACCEPTED`，收口 Commit `411535b32db4a40991e3c64228d018e9cebb17ed` 已存在于当前历史。Task 12 主任务仍为 `IN_PROGRESS / codex`；在负责人最终验收、`390 × 844` 窄屏视觉验收或负责人书面豁免、Gitee 当前远端 HEAD 核验及本轮必要治理同步完成前，不得标记为 `DONE`、`ACCEPTED` 或 `SYNCED`。

## 6. Task 13 既有实现登记

以下提交已逐个核验并保留，但均不等同于正式验收通过：

| Commit | 实际功能 | 历史测试证据 | 当前结论 |
| --- | --- | --- | --- |
| `031a4fca26cebcaf5b67091142ac6b3b82c9cbaa` | Reviewer 空间 Scope、动作权限及审核唯一约束基础 | `735 passed`、`9 skipped`、`582 subtests` | 已有实现，持久 PostgreSQL 迁移前置检查和独立验收未完成 |
| `95af9ca7c06eced103a7a034482959c97df04852` | AuditEvent、Outbox、幂等持久化基础 | `761 passed`、`9 skipped`、`585 subtests` | 已有实现，未连接持久 PostgreSQL，Worker/通知不在实现内 |
| `6d6bb9808ef68b87de63cf1d1762105aa9f8485a` | `DRAFT → IN_REVIEW` 提交审核 Service | `785 passed`、`9 skipped`、`624 subtests` | 已有实现，无 HTTP/UI，真实 PostgreSQL 并发未验收 |
| `e88bf8e065807343a5b78a0a49c29d0824980b67` | 驳回、审核记录、后继 Draft、审计/Outbox/幂等 | `800 passed`、`9 skipped`、`657 subtests` | 已有实现，Approve-vs-Reject 等 PostgreSQL 竞争未验收 |
| `e422b16ba0826064a629604a217b93978101d5f7` | 原子批准发布/重新发布及新工作 Draft | `818 passed`、`9 skipped`、`697 subtests` | 已有实现，双 Reviewer、锁等待和事务隔离未验收 |
| `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e` | 待审、审核详情、已审核、提交状态、驳回上下文 Reader | `827 passed`、`9 skipped`、`712 subtests` | 已有实现，无 HTTP/UI，尚待独立验收 |

ADR-0004 证明负责人选择了 Reviewer Scope 方案 B，但现有资料未发现六项实现各自完整的历史开工授权或负责人独立验收记录。本轮只确认保留与登记，不改变 Task 13 的 `BACKLOG / unassigned` 状态。

归档前原始文件 `apps/workflow/tests/test_pg_concurrency.py` 的 Git 来源无法确认，SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`。Task 13-08-002 已验证的修正隔离副本 SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`；两个摘要对应不同字节版本。原始版本已在独立 Evidence 目录备份，修正版本已由单文件 Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 正式纳入 Git。


## 7. Task 13-07 验收结论与历史现场

### 7.1 001 历史现场（BLOCKED，原样保留）

- 001 在基线 `04e363b5976536de34aede336e49c6747cede521` 上因指定 Worktree 和 Evidence 在资源门禁检查时已经存在而停止；未启动 PostgreSQL、未执行 Migration 或并发测试。
- `D:\Temp\OpsAI-Task13-07-001-Workspace` 保持 detached HEAD `04e363b5976536de34aede336e49c6747cede521`，已跟踪工作区和索引无修改；两个未跟踪文件保持原样。
- `D:\Temp\OpsAI-Task13-07-001-Evidence\preflight.md` 保持原样，SHA-256 为 `F7EB5604523EBEECB155DE69DEE3C3A7884CC6B813B12F3AD897797C8EAF584E`。
- 001 Worktree、Evidence 及其内容不得删除、移动、覆盖、清理、执行或复用。

### 7.2 Task 13-07-002 验收结果（FAILED）

- 运行标识：`TASK13-07-ISOLATED-PG-002`。
- 执行基线：`9fbc74843c339bc712ca59dc67e7bc28e22ef9d8`。
- 实际测试：14 项执行，6 PASS、7 FAIL、1 ERROR、0 SKIPPED；没有重跑。
- 正式结论：`FAILED`。Task 13-07 历史状态继续登记为 `BLOCKED / unassigned`；其暴露的行锁缺陷已有 Task 13-08 后继核心修复及 13-08-002 的 14 PASS 证据，但不得据此改写 13-07 历史结果或自动重跑。
- 已确认 PostgreSQL 错误：`FOR UPDATE cannot be applied to the nullable side of an outer join`。
- 根因：Submit 与 Reject 的 Article 加锁查询使用 `select_related("space", "current_published_version")`；`current_published_version` 为可空关联，使 PostgreSQL 拒绝在该外连接的可空侧应用 `FOR UPDATE`，相关路径返回 `WORKFLOW_UNAVAILABLE`。
- Approve/Publish 的 Article 加锁查询只联表加载 `space`，其主要并发场景通过；本轮缺陷修复不得擅自修改 Approve/Publish。
- 证据来源：`D:\Temp\OpsAI-Task13-07-002-Evidence\execution-results.md` 与 `final-state.md`。002 Worktree、Evidence 和已停止容器均保留用于审计，本轮不得操作、覆盖或清理。
- Task 13-07-002 当时使用的原始测试文件与 002 副本 SHA-256 均为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`；该摘要继续作为历史失败证据保留，不因后续归档而改写。

## 8. Task 13-08 完成证据

### 8.1 核心修复

- 核心 Commit：`1050b8fbf1fc384a79a90fcc86ae9320e5afb67e`。
- 实际修改：`apps/workflow/services.py`、`apps/workflow/tests/test_submit_service.py`、`apps/workflow/tests/test_reject_service.py`。
- 实现内容：从 Submit/Reject 的 Article 加锁查询 `select_related` 中移除 `current_published_version`，只保留 `space`；Article 行锁和事务边界保持不变。
- Commit 内验证：RED 2 项失败、GREEN 2 项通过；Submit/Reject 39 项、审核/权限/幂等及 Approve/Publish 63 项、Task 12 版本链 97 项，共 199 项唯一测试通过。

### 8.2 PostgreSQL 修正夹具复验

- Task 13-08-001：在 HEAD `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 使用原始哈希副本执行 14 项，结果为 13 PASS、1 FAIL、0 ERROR、0 SKIPPED；PG07 暴露 Article 初始标题与旧 `PUBLISHED` 版本标题不一致。
- Task 13-08-002：在同一 HEAD 使用可追溯修正副本执行 14 项，结果为 14 PASS、0 FAIL、0 ERROR、0 SKIPPED；原可空外连接行锁错误未再出现。
- 修正副本只调整 PG07 初始 `Article.title` 与当前 `PUBLISHED` 版本标题投影一致性；隔离副本 SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`。
- 上述证据完成 Task 13-08 核心修复验收；正式仓库中的 PG07 测试文件随后由独立归档 Commit 完成纳管，但这仍不等于 Task 13 主任务完成。

## 9. Task 13-08-ARCHIVE 完成记录

该后继任务已在负责人针对精确基线单独授权后完成；以下记录归档边界和可核验证据，不构成再次执行授权。

- 归档 Commit：`a066b8e158d53770b2f9dab5e2c7e70c87817975`；父提交：`8049e17eabf97148b42a6c6b0196ac098bf1613c`。
- 唯一归档文件：`apps/workflow/tests/test_pg_concurrency.py`；Commit 仅新增该文件，Git 提交统计为新增 993 行。
- 已归档 SHA-256：`4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`；与批准来源逐字节一致。
- 归档前原始版本 SHA-256：`08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`；原始版本已在独立 Evidence 目录备份。
- Python 编译、Ruff lint、Ruff format check 和 Git 检查通过。本次归档没有重新执行 PostgreSQL；14/14 PASS 是 Task 13-08-002 修正副本的历史验证证据。
- 归档没有重复运行或重新实现 Task 13-08 核心修复；此前失败、复验、Worktree 和 Evidence 历史事实保持不变。

继续禁止修改业务实现、其他测试、治理文件以外的文件、历史 Evidence、临时 settings 或数据库文件；禁止 Push、Merge、Reset、Clean，不得自动启动 HTTP/UI 或其他任务。

## 10. 持续边界

- Task 12 历史成果全部保留，主任务继续为 `IN_PROGRESS / codex`；尚缺负责人最终验收、`390 × 844` 窄屏视觉验收或书面豁免、Gitee 当前远端核验及必要治理同步，不得标记为 DONE。
- Task 13 主任务继续为 `BACKLOG / unassigned`；Task 13-08 核心修复与 Task 13-08-ARCHIVE 归档均为 `DONE / unassigned`，但不代表 Task 13 全面完成。
- 001 和 002 的 Worktree、Evidence、未跟踪文件与 002 已停止容器必须原样保留，不得覆盖或清理。
- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- 不读取真实 `.env`，不连接 PostgreSQL，不启动新数据库容器，不执行 Migration，不开发审核工作台。
- 本轮治理 Commit 完成后立即停止；P3-UI-02 仅为下一项试点候选，未获得独立授权前不得执行，不 Push、Merge、Reset 或 Clean。`docs/HANDOFF.md` 只能用于人工接力，不能授予自动执行权。
