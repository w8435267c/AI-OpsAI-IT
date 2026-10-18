# OpsAI Current Task

> Task 12“开发文章创建、草稿和版本保存”当前继续为 `IN_PROGRESS / codex`。Task 12A～12E 的历史成果保留，Task 12E 收口 Commit 为 `411535b32db4a40991e3c64228d018e9cebb17ed`。Task 13 仍为 `BACKLOG / unassigned`；其六个既有提交仅登记为“已有实现、待治理确认与独立验收”，不追认现有资料未证明的历史开工授权。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `12` |
| 任务名称 | 开发文章创建、草稿和版本保存 |
| 优先级 | `MUST` |
| 当前状态 | `IN_PROGRESS` |
| 当前负责人 | `codex` |
| 开工日期 | `2026-10-05` |
| 直接依赖 | Task 11，`DONE / codex` |
| 当前分支 | `fusion/wagtail-poc` |
| 本轮治理核验代码基线 | `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e` |
| 远端核验 | GitHub 实时 HEAD 为 `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e`；Gitee 因 SSL 连接错误为 `UNKNOWN`，不得宣称三端同步 |
| 当前主阶段 | Task 12 |
| 已完成阶段 | Task 12A～12E；Task 12E 为 `DONE / ACCEPTED` |
| 当前收口 | Task 12 主任务尚缺负责人最终验收、`390 × 844` 窄屏视觉验收或负责人书面豁免、Gitee 当前远端 HEAD 核验及必要治理文件同步 |
| 本轮唯一授权 | Task 12/13 治理对齐与历史成果登记；仅文档与一次本地 Commit，完成后停止 |
| 下一候选技术验收 | Task 13-07；尚未获执行授权，不得运行未跟踪 PostgreSQL 测试 |

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

未跟踪文件 `apps/workflow/tests/test_pg_concurrency.py` 的 SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`，疑似 Task 13-07 验收草稿；现有资料无法确认 Git 来源，尚未执行、尚未验收，必须保持未跟踪。后续仅可在负责人另行授权的一次性隔离 PostgreSQL 环境中运行。

## 7. 持续边界

- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- Task 13 已存在上述六项底层实现，但不得据此继续开发、补 UI、运行 PostgreSQL 专项或宣称验收通过。
- 不读取或记录真实 `.env` 正文，不把临时 PostgreSQL 证据写成持久环境验收。
- 不把仓库外截图、SQLite、settings、临时脚本或浏览器日志提交 Git。
- 未经授权不 Push，不执行 Task 13-07，不宣称 Task 12、Task 13 或整个项目已 DONE / 上线就绪。
