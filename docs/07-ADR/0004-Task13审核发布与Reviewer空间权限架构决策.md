# ADR-0004：Task 13 审核发布与 Reviewer 空间权限架构决策

- 状态：Accepted
- 决策日期：2026-10-12
- 适用任务：Task 13 — 提交审核、批准、驳回和发布事务
- 本次落地范围：Task 13-02A 的审核权限与核心 Schema 底座
- 不代表：提交、驳回、批准发布、审核队列、审计、Outbox 或通知已经实现

## 1. 背景

Task 12 已建立 `Article + ArticleVersion` 正式内容权威、不可变版本节点和员工只读
`current_published_version` 的边界。Task 13 需要在此基础上实现提交、审核与发布，
但必须先冻结 Reviewer 的对象范围、动作权限和数据库安全兜底。

Owner 已选择 Reviewer Scope 方案 B：Reviewer 按 `KnowledgeSpace` 授权，同一空间内
所有具有有效 Scope 的 Reviewer 共享该空间的待审池。

## 2. Reviewer 对象范围

采用独立关联模型 `ReviewerSpaceScope`，表达一个用户在一个知识空间拥有 Reviewer
对象范围。

- 同一 `reviewer + space` 只能存在一条记录；停用后重新授权应启用原记录，不创建重复行。
- `is_active` 用于软停用；V1 不增加生效时间、失效时间或到期时间。
- V1 不做 Article 或 ArticleVersion 级 Reviewer 指定。
- V1 不做独占 Reviewer、自动抢单或 assignee。
- 同一 Space 的有效 Reviewer 共享待审池。

Scope 只表达对象范围，不自动添加 Django Group，也不自动授予 Permission。正式审核
授权必须同时满足：Reviewer 业务角色、必要动作 Permission、目标 Space 的有效 Scope。

## 3. 动作权限

`ArticleVersion` 定义以下自定义动作权限：

- `submit_articleversion`
- `review_articleversion`
- `approve_articleversion`
- `reject_articleversion`
- `publish_articleversion`

角色映射如下：

| 角色 | Submit | Review | Approve | Reject | Publish |
| --- | --- | --- | --- | --- | --- |
| Editor | 是 | 否 | 否 | 否 | 否 |
| Reviewer | 否 | 是 | 是 | 是 | 是 |
| Knowledge Admin | 是 | 否 | 否 | 否 | 否 |
| Employee | 否 | 否 | 否 | 否 | 否 |

Knowledge Admin 不因管理员身份自动成为 Reviewer。`is_staff` 或 `is_superuser` 也不构成
业务审核授权；后续 Service 必须显式校验业务角色，不能只调用 `has_perm()`。

## 4. 核心数据库约束

- 每个 Article 最多存在一个 `IN_REVIEW` ArticleVersion。
- 每个 ArticleVersion 最多存在一个 `content_review` ReviewRecord。
- `periodic_review` 和 `emergency_review` 不受 content review 唯一约束限制。
- 既有每 Article 最多一个 `DRAFT`、最多一个 `PUBLISHED` 的约束保持不变。

这些约束是重复提交、重复审核和批准/驳回竞争的数据库兜底，不替代未来 Service 的
状态、权限、幂等和事务校验。

## 5. 状态机决定

Task 13 延续以下状态规则：

1. Submit 执行 `DRAFT → IN_REVIEW`，并把 `latest_working_version` 设为 `NULL`。
2. `IN_REVIEW` 期间没有可编辑工作 Draft。
3. Reject 执行 `IN_REVIEW → REJECTED`；REJECTED 历史不可变，后续创建新的 DRAFT。
4. Reject 原因必填。
5. Approve 与 Publish 是同一个原子动作，不新增 `APPROVED` 状态。
6. Republish 时旧 `PUBLISHED → SUPERSEDED`，新 `IN_REVIEW → PUBLISHED`。
7. Employee 与 Search 始终只认 `Article.current_published_version`。

## 6. 正式边界

- Wagtail 不进入正式 Task 13 实现，不建立第二套审核或发布状态机。
- `ReviewRecord` 继续表示审核结论，不新增 `submitted` 或 `published` decision。
- 本阶段不增加 Reject 派生血缘字段，也不复用 `restored_from_version` 表示拒绝派生。
- 本阶段不实现 Reviewer 授权 Resolver、Review Queue、Review Detail、HTTP 或 UI。
- AuditEvent、Outbox 和 Idempotency 由 Task 13-02B 单独设计和实现。
- Submit、Reject、Approve/Publish 的正式 Service 属于后续独立子任务。

## 7. 数据迁移与部署

Task 13-02A 只增加 Scope 模型、两个条件唯一约束和动作权限元数据，不写数据清理
`RunPython`。

向共享持久数据库应用迁移前必须只读检查：

- 是否存在同一 Article 的多个 `IN_REVIEW` 版本；
- 是否存在同一 ArticleVersion 的多个 `content_review` 记录。

未完成上述检查前，不声明持久数据兼容。SQLite 验证只证明通用迁移与约束行为，
不能替代 PostgreSQL 并发和锁验证。

## 8. 影响

本决策建立 Task 13 的最小授权和 Schema 底座，但系统仍不会真正提交审核或发布。
后续 Service 必须在事务内组合角色、动作权限、有效 Space Scope、作者/提交者隔离、
状态校验、审计、Outbox 和幂等；任何单项通过都不能单独证明审核授权成立。
