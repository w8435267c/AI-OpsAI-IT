# OpsAI Current Task

> 当前唯一后继候选修复任务为 Task 13-08“PostgreSQL 可空关联行锁最小修复”，状态为 `READY / unassigned`。本轮只完成 Task 13-07 失败后的治理交接，不授权 Task 13-08 业务代码修改；真实开发必须等待项目负责人针对本次治理 Commit 后的新 40 位完整 HEAD 再次明确授权。Task 12 保持 `IN_PROGRESS / codex`，Task 13 主任务保持 `BACKLOG / unassigned`，不追认六个既有 Task 13 提交的历史开工授权或负责人验收。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `Task 13-08` |
| 任务名称 | PostgreSQL 可空关联行锁最小修复 |
| 优先级 | `MUST` |
| 当前状态 | `READY / unassigned`；仅登记为 Task 13-07 失败后的唯一后继候选修复任务，尚未获得业务代码修改授权 |
| 当前负责人 | `unassigned` |
| 治理登记日期 | `2026-10-19` |
| 前置例外 | 项目负责人允许在 Task 12 尚未封板、Task 13 主任务仍为 `BACKLOG` 时登记这一局部缺陷修复例外；不代表 Task 13 全面开工 |
| 当前分支 | `fusion/wagtail-poc` |
| 本轮批准起始 HEAD | `9fbc74843c339bc712ca59dc67e7bc28e22ef9d8` |
| 前置验收结果 | Task 13-07-002 为 `FAILED`：14 项执行、6 PASS、7 FAIL、1 ERROR；Task 13-07 转为 `BLOCKED / unassigned` |
| 正式任务状态 | Task 12 为 `IN_PROGRESS / codex`；Task 13 为 `BACKLOG / unassigned` |
| 已确认根因 | PostgreSQL 报错 `FOR UPDATE cannot be applied to the nullable side of an outer join`；Submit/Reject 的 Article 行锁查询联表加载可空 `current_published_version` |
| 批准设计方向 | 方案 B：从 Submit/Reject 的 Article 加锁查询 `select_related` 中移除 `current_published_version`，只保留 `space` |
| 未来允许修改文件 | `apps/workflow/services.py`、`apps/workflow/tests/test_submit_service.py`、`apps/workflow/tests/test_reject_service.py`；须等待新的逐次授权 |
| Task 13-08 开发起始 HEAD | 待本次治理 Commit 形成后填写；负责人必须另行批准该新 40 位完整 HEAD |
| 当前允许动作 | 仅修改 `tasks/CURRENT_TASK.md` 与 `tasks/TASKS.yaml`，完成治理验证后创建一次本地治理 Commit；不授权业务代码、PostgreSQL、Docker、Migration、HTTP/UI 或 Push。 |

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

未跟踪文件 `apps/workflow/tests/test_pg_concurrency.py` 的 Git 来源仍无法确认，SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`。Task 13-07-002 已按授权在隔离 Worktree 中执行哈希一致的副本；正式仓库原文件未被执行、修改、暂存或提交，必须继续保持未跟踪。


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
- 正式结论：`FAILED`。Task 13-07 状态登记为 `BLOCKED / unassigned`，等待 Task 13-08 完成行锁缺陷修复后，由负责人另行授权全新的 PostgreSQL 17.11 并发复验。
- 已确认 PostgreSQL 错误：`FOR UPDATE cannot be applied to the nullable side of an outer join`。
- 根因：Submit 与 Reject 的 Article 加锁查询使用 `select_related("space", "current_published_version")`；`current_published_version` 为可空关联，使 PostgreSQL 拒绝在该外连接的可空侧应用 `FOR UPDATE`，相关路径返回 `WORKFLOW_UNAVAILABLE`。
- Approve/Publish 的 Article 加锁查询只联表加载 `space`，其主要并发场景通过；本轮缺陷修复不得擅自修改 Approve/Publish。
- 证据来源：`D:\Temp\OpsAI-Task13-07-002-Evidence\execution-results.md` 与 `final-state.md`。002 Worktree、Evidence 和已停止容器均保留用于审计，本轮不得操作、覆盖或清理。
- 原始未跟踪测试文件与 002 副本 SHA-256 均为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`；正式仓库中的原文件继续保持未跟踪、未修改、未暂存。

## 8. Task 13-08 开发合同（仅登记，未授权执行）

### 8.1 目标与方案

- 任务名称：Task 13-08 — PostgreSQL 可空关联行锁最小修复。
- 目标：消除 Submit、Reject 中由 `current_published_version` 可空关联造成的 PostgreSQL `FOR UPDATE` 错误。
- 批准方案 B：从 Submit/Reject 的 Article 加锁查询 `select_related` 中移除 `current_published_version`，只保留 `space`。
- 必须保留 Article 行锁、现有事务边界、审核状态机、权限判断、幂等、Audit 与 Outbox 行为。

### 8.2 未来授权范围

未来只有在负责人批准本次治理 Commit 后的新 40 位完整 HEAD 时，才允许修改：

- `apps/workflow/services.py`
- `apps/workflow/tests/test_submit_service.py`
- `apps/workflow/tests/test_reject_service.py`

禁止改变 Model 或 Migration，禁止修改 Approve/Publish，禁止开发 HTTP/UI，禁止修改正式数据库或原始 PostgreSQL 并发测试。

### 8.3 未来验收条件

1. Submit/Reject 专项测试通过。
2. 相关审核、权限、幂等回归通过。
3. Approve/Publish 回归通过。
4. Task 12 版本链相关回归通过。
5. Django check 与迁移一致性检查通过。
6. Ruff、格式、Git 修改范围和 `git diff --check` 通过。
7. 创建一个范围单一、说明完整的本地代码 Commit。
8. PostgreSQL 17.11 并发复验由负责人后续另行授权，不属于 Task 13-08 代码修复轮次。

## 9. 持续边界

- Task 12 历史成果全部保留，主任务继续为 `IN_PROGRESS / codex`；尚缺负责人最终验收、`390 × 844` 窄屏视觉验收或书面豁免、Gitee 当前远端核验及必要治理同步，不得标记为 DONE。
- Task 13 主任务继续为 `BACKLOG / unassigned`；Task 13-08 只是本次失败直接产生的局部缺陷修复例外，不代表 Task 13 全面开工。
- 001 和 002 的 Worktree、Evidence、未跟踪文件与 002 已停止容器必须原样保留，不得覆盖或清理。
- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- 不读取真实 `.env`，不连接 PostgreSQL，不启动新数据库容器，不执行 Migration，不开发审核工作台。
- 本轮治理 Commit 完成后立即停止；未获得对新完整 HEAD 的再次授权前，不执行 Task 13-08 业务代码修复，不 Push、Merge、Reset 或 Clean。
