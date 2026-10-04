# OpsAI Current Task

> 项目负责人已正式授权 Task 11“开发 P0 搜索”进入 `IN_PROGRESS / codex`。本轮仅完成开工状态切换，尚未进入 Task 11A 或任何搜索业务实现。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `11` |
| 任务名称 | 开发 P0 搜索 |
| 优先级 | `MUST` |
| 当前状态 | `IN_PROGRESS` |
| 当前负责人 | `codex` |
| 开工日期 | `2026-10-04` |
| 直接依赖 | Task 10，`DONE / codex` |
| 范围冻结 Commit | `5266c278803b16a3c0ec4a0eaffdcb16d641580c`，已双端同步 |
| 当前实施状态 | 仅完成任务状态切换；搜索业务代码尚未开始 |

Task 10 已正式封板为 `DONE / codex`，Task 11 的唯一登记依赖已经满足。依赖满足与正式开工授权均已具备，但本轮授权范围只包含状态切换和元数据同步；后续 Task 11 实施阶段仍须由项目负责人单独授权。

## 2. V1 搜索范围

Task 11 V1 只允许搜索当前正式发布版本中的以下字段：

- `current_published_version.title`
- `current_published_version.summary`
- `current_published_version.body_plaintext`

当前正式模型没有已确认可用的标签或别名字段，因此 V1 不实现标签、别名或同义词搜索，也不得为其新增 Model、Field、中间表或 Migration。

## 3. 权限与正式版本契约

正式员工搜索顺序固定为：

```text
request.user
↓
employee_visible_articles(...)
↓
current_published_version
↓
title / summary / body_plaintext
↓
搜索
↓
排序
↓
分页
↓
展示
```

必须先完成权限过滤，再执行搜索、统计、排序和分页。页面只允许显示当前员工可见结果数量，不得泄露标题、摘要、正文片段、DENY 文章、草稿、全库匹配总数或隐藏分页信息。

Published A 同时存在 Draft B 时，只能命中和展示 Published A；仅存在于 Draft B、`latest_working_version` 或历史版本中的关键词不得让该 Article 出现在员工搜索结果中。详情跳转继续使用 `/kb/<kb_no>/`，并由现有正式详情链路重新鉴权。

## 4. 日志与数据库边界

- `apps/search` 与 `apps/audit` 当前没有已确认可直接复用的正式搜索或点击日志模型。
- 如搜索或点击日志需要新增 `SearchLog`、`ClickLog`、`AuditEvent`、数据库表或 Migration，必须停止并提出 `SCOPE QUESTION`，等待项目负责人授权。
- Task 11 第一阶段可使用 Django 与 SQLite 测试数据库验证功能、权限、安全、页面和自动测试。
- SQLite 结果不能证明 PostgreSQL 全文检索、相关性排序、索引、中文检索行为或性能。
- PostgreSQL、Docker、真实 migration 和持久数据访问当前均未授权；Task 8J 保持 `BLOCKED / unassigned`。

## 5. 当前边界与下一步

- Task 10：`DONE / codex`。
- Task 11：`IN_PROGRESS / codex`，当前唯一进行中任务。
- Task 8J：`BLOCKED / unassigned`。
- Task 12：`BACKLOG / unassigned`，不得提前启动。
- 本轮未创建或修改任何搜索业务代码、路由、模板、测试、Model 或 Migration。
- 不读取 `.env` 或 `OpsAI.env`，不启动 PostgreSQL 或 Docker，不执行真实 `migrate`。
- 下一步必须等待项目负责人单独授权 Task 11 的具体实施阶段，不得自行开始 Task 11A、Task 11B 或扩大冻结范围。

## 6. 状态流转

### IN_PROGRESS

当前状态。项目负责人已正式授权 Task 11 开工，负责人为 `codex`；本轮仅完成状态切换，业务实现尚未开始。

### VERIFY

未来状态。只有 Task 11 获授权范围内的业务实现、自动验证和验收证据齐备后，才可由项目负责人授权进入。

### DONE

未来状态。必须等待项目负责人最终验收，不得由执行 Agent 自行切换。
