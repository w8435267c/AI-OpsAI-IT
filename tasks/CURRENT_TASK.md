# OpsAI Current Task

> Task 12“开发文章创建、草稿和版本保存”当前为 `IN_PROGRESS / codex`。Task 12A～12D 已 `DONE / SYNCED`；下一阶段是 Task 12E，当前仅为 `NEXT / NOT STARTED`。

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
| 当前同步基线 | `1e025b9f9a96f7c63207a196dcfd916553940004`，LOCAL / GitHub / Gitee 三端同步 |
| 当前主阶段 | Task 12 |
| 已完成阶段 | Task 12A～12D |
| 下一阶段 | Task 12E，`NEXT / NOT STARTED` |

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

## 5. 下一阶段：Task 12E

Task 12E 当前为 `NEXT / NOT STARTED`，目标范围是：

1. 正式编辑器 UI 与草稿编辑入口；
2. 接入 autosave / manual save Service；
3. 历史版本查看与恢复入口；
4. 草稿预览；
5. 保持员工正式发布内容隔离；
6. 完成视觉 / 人工验收与 Task 12 最终 closeout。

本轮仅同步状态，不开始 Task 12E。Task 12 仍为 `IN_PROGRESS / codex`，Task 13 仍为 `BACKLOG / unassigned`。

## 6. 持续边界

- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- submit、review、approve、reject、publish、republish 属于 Task 13，本阶段不得实现。
- 不读取或记录真实 `.env` 正文，不把临时 PostgreSQL 证据写成持久环境验收。
- 未经授权不 Push，不开始 Task 13，不宣称 Task 12 已 DONE。
