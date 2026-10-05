# OpsAI Current Task

> Task 12“开发文章创建、草稿和版本保存”已由项目负责人正式授权进入 `IN_PROGRESS / codex`。Task 12A 架构冻结已 `DONE / SYNCED`；当前阶段为 Task 12B，但尚未开始业务实现，下一动作是等待项目负责人单独授权 Task 12B。

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
| Task 12A | 正式写入契约与融合范围冻结，`DONE / SYNCED` |
| 架构决策 | `docs/07-ADR/0003-Task12正式文章写入与版本链架构决策.md`，`Accepted` |
| ADR Commit | `72029527406c17f433c3226475609a291373b55e`，LOCAL / GitHub / Gitee 三端同步 |
| 当前阶段 | Task 12B — 最小 Model / Migration 增量 |
| 当前实施状态 | `NOT STARTED`；本轮只完成 Task 12 主任务开工登记 |

## 2. Task 12A 已冻结架构

- 正式内容权威为 `Article + ArticleVersion`。
- `Article` 负责稳定身份；`ArticleVersion` 负责版本化内容权威。
- 现有 `body` 是正文权威；`body_plaintext` 是服务端派生投影。
- `Article.latest_working_version` 继续作为当前工作草稿指针，不新增同义 `current_working_version` 字段。
- `Article.current_published_version` 继续作为员工正式发布指针，Task 12 不改变其发布语义。
- Task 12 V1 不正式接入 Wagtail，不增加正式 Wagtail Model、依赖、settings、URL、Admin 或 Revision 双写。

## 3. KB 编号与版本合同

- KB 编号格式为 `KB-000001`，全局唯一、不可修改、仅由服务端生成并允许 Gap。
- 后续方案为 `KnowledgeNumberCounter + 数据库锁 + 事务 + Article.kb_no 唯一约束`。
- autosave 原地更新当前 `DRAFT`，必须使用 `lock_version / expected_lock_version`。
- 并发冲突明确失败，不允许 last-write-wins、静默覆盖或自动合并。
- manual save 语义为 `DRAFT → 不可变 SAVED → 新 DRAFT`。
- 历史恢复复制旧版本内容生成新版本号的新 DRAFT，并通过 `restored_from_version` 保留来源；旧历史不得修改。

## 4. Task 12 阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 12A | 正式写入契约与融合范围冻结 | `DONE / SYNCED` |
| 12B | 最小 Model / Migration 增量 | `NEXT / NOT STARTED` |
| 12C | KB 编号服务与原子 Article 创建 | 未开始 |
| 12D | manual save、autosave、乐观锁和历史恢复 | 未开始 |
| 12E | 正式编辑页面、草稿预览与 Task 12 收口 | 未开始 |

不得跳过 12B 直接进入 12C。

## 5. Task 12B 预定范围

Task 12B 只允许在下一轮单独授权后评估和实施 ADR 已批准的最小结构：

1. `KnowledgeNumberCounter`；
2. `ArticleVersion.lock_version`；
3. `ArticleVersion.restored_from_version`；
4. `SAVED` 状态及必要约束；
5. `latest_working_version` 必要模型约束。

当前这些内容均未实现。本轮不得修改 `apps/knowledge/models.py`，不得生成 Migration。

## 6. Task 13 与环境边界

- Task 12 不实现提交审核、批准、驳回、发布或重新发布；这些全部属于 Task 13。
- Task 13 保持 `BACKLOG / unassigned`。
- 8J 保持 `BLOCKED / unassigned`。
- Task 12 普通开发不读取真实 `.env` 或 `OpsAI.env`，不操作持久 PostgreSQL、Docker、真实 5432 或持久 Volume。
- KB 编号并发、乐观锁、Migration 和必要事务行为在封板前需要另行授权的临时隔离 PostgreSQL 验证；该验证不解除 8J。

## 7. 当前允许与禁止

当前只完成 Task 12 开工状态和架构基线登记。等待项目负责人单独授权 Task 12B。

禁止：

- 提前开始 Task 12B；
- 修改 Model 或生成 Migration；
- 实现 KB 编号服务、lock_version、SAVED 或 restored_from_version；
- 正式接入 Wagtail；
- 开始 Task 13；
- 操作数据库或 Docker；
- 未经授权 Push。

## 8. 状态流转

### IN_PROGRESS

当前状态。Task 12 已正式开工，由 `codex` 负责；Task 12A 已完成，Task 12B 尚未开始。

### VERIFY

尚未进入。必须等待 Task 12B～12E 按独立授权完成并形成充分验证证据。

### DONE

尚未进入。代码完成不等于 DONE，仍需自动验证、环境专项、负责人验收、状态归档和获授权的双端同步。
