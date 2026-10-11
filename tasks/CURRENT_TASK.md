# OpsAI Current Task

> Task 12“开发文章创建、草稿和版本保存”当前为 `IN_PROGRESS / codex`。Task 12A～12E 已完成；Task 12E 为 `DONE / ACCEPTED`，本次 12E-09B 纯文档收口 Commit 待同步。Task 13 仍为 `BACKLOG / unassigned`。

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
| 当前同步业务基线 | `4e4a0bd25abed587c587c8bfc419b3ebe583198d`，LOCAL / GitHub / Gitee 三端同步 |
| 当前主阶段 | Task 12 |
| 已完成阶段 | Task 12A～12E；Task 12E 为 `DONE / ACCEPTED` |
| 当前收口 | Task 12E-09B，纯文档 Commit 待同步 |
| 下一主要功能阶段 | Task 13，`BACKLOG / unassigned`，未授权开始 |

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

Task 12E 已 `DONE / ACCEPTED`，本次 Task 12E-09B 纯文档收口 Commit 待后续双端同步。Task 12 仍为 `IN_PROGRESS / codex`。

## 6. 持续边界

- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- submit、review、approve、reject、publish、republish 属于 Task 13，本阶段不得实现。
- 不读取或记录真实 `.env` 正文，不把临时 PostgreSQL 证据写成持久环境验收。
- 不把仓库外截图、SQLite、settings、临时脚本或浏览器日志提交 Git。
- 未经授权不 Push，不开始 Task 13，不宣称 Task 12 或整个项目已 DONE / 上线就绪。
