# OpsAI Current Task

> Task 11“开发 P0 搜索”的业务功能、自动验证、负责人视觉验收和 PostgreSQL 隔离专项均已完成并通过项目负责人最终验收，当前状态为 `DONE / codex`。当前没有活动任务，下一业务任务尚未授权。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `11` |
| 任务名称 | 开发 P0 搜索 |
| 优先级 | `MUST` |
| 当前状态 | `DONE` |
| 当前负责人 | `codex` |
| 开工日期 | `2026-10-04` |
| 直接依赖 | Task 10，`DONE / codex` |
| 范围冻结 Commit | `5266c278803b16a3c0ec4a0eaffdcb16d641580c`，已双端同步 |
| 当前实施状态 | Task 11A、11B、负责人视觉验收和 PostgreSQL 隔离专项全部 PASS；Task 11 已最终封板 |

Task 10 已正式封板为 `DONE / codex`，Task 11 的唯一登记依赖已经满足。Task 11 V1 不需要 Task 11C；分类筛选为可选项，标签、别名、同义词和 HTML 高亮按冻结范围延期，搜索/点击日志不是 V1 MUST。

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
- Task 11 通用功能、权限、安全、页面和自动测试已使用 SQLite 完成验证。
- Task 11P-1 已在仓库外临时 PostgreSQL 17.11 环境补齐当前 `icontains` 方案的 Migration、中文 substring、权限隔离、排序、查询计划和 1,000 篇合成数据性能证据；该结果不等于 PostgreSQL FTS、生产容量或真实持久环境已验证。
- 真实 PostgreSQL、真实 `.env`、持久 migration 和持久数据访问仍未授权；Task 8J 保持 `BLOCKED / unassigned`。

## 5. 实施与验证证据

- Task 11A：`DONE / SYNCED`，Commit `6240147054f909c9f88c14d67e99f7c55ccc83d1`，搜索 Reader 专项 `13 passed / 16 subtests`。
- Task 11B：`DONE / SYNCED`，Commit `7ac5cd894db052dc3c7eb7e2721dbcc4f34d7ea6`，搜索页面专项 `13 passed / 11 subtests`。
- knowledge 回归：`310 passed / 59 subtests`；正式工程回归：`486 passed / 102 subtests`。
- 项目负责人视觉验收：`PASS`；网络搜索 21 条并按 20+1 分页，打印机搜索 1 条，零结果、Draft-only 隔离和 KB-910001 正式详情链路均通过。
- Reader 在 3 条和 23 条结果时均为 1 query；页面在 3 条和 23 条结果时均为 4 queries，无 N+1。
- PostgreSQL 隔离专项：`PASS`；PostgreSQL 17.11 临时环境中 Migration、Task 11A `13 passed / 16 subtests`、Task 11B `13 passed / 11 subtests`、行为矩阵、EXPLAIN/ANALYZE 和 1,000 篇合成数据性能证据均通过，临时资源已全部清理。

## 6. 当前边界与下一步

- Task 10：`DONE / codex`。
- Task 11：`DONE / codex`，最终验收与封板已完成。
- Task 8J：`BLOCKED / unassigned`。
- Task 12：`BACKLOG / unassigned`，不得提前启动。
- PostgreSQL 隔离专项为 `PASS`；当前 V1 不要求改为 PostgreSQL FTS，也未新增 SearchVector、GIN、Model 或 Migration。
- 不读取 `.env` 或 `OpsAI.env`，不启动 PostgreSQL 或 Docker，不执行真实 `migrate`。
- 当前不存在 `IN_PROGRESS` 或 `VERIFY` 任务。
- 下一业务任务尚未授权；不得开始 Task 11C 或 Task 12。

## 7. 状态流转

### IN_PROGRESS

历史状态。Task 11A、Task 11B 开发期间由 `codex` 负责实施。

### VERIFY

历史状态。Task 11 V1 业务功能和负责人视觉验收通过后，等待 PostgreSQL 隔离专项验证期间处于 `VERIFY / codex`。

### DONE

当前状态。Task 11A、Task 11B、负责人视觉验收和 PostgreSQL 17.11 隔离专项全部 PASS，项目负责人已授权并完成 Task 11 最终封板。
