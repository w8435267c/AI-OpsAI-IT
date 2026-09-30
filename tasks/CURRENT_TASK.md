# OpsAI Current Task

> 当前唯一已授权 `IN_PROGRESS` 任务为 Task 10。本轮只完成开工状态切换与接力元数据同步，尚未开始页面业务代码开发。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `10` |
| 任务名称 | 开发首页、分类页和正式知识详情页 |
| 优先级 | `MUST` |
| 当前状态 | `IN_PROGRESS` |
| 当前负责人 | `codex` |
| 开工日期 | `2026-09-30` |
| 依赖 | 任务 `9`，当前为 `DONE` |
| 任务来源 | `tasks/TASKS.yaml` |
| 选择依据 | 项目负责人正式选择 Task 10，并授权 `BACKLOG → IN_PROGRESS` |

项目负责人已正式选择 Task 10 作为下一根接力棒，并授权 Codex 接手。当前状态切换只确认任务身份、范围和安全边界，不代表首页、分类页或正式知识详情页已经实现。

## 2. 任务目标

使用 Django Templates、Bootstrap 和 HTMX 建立正式员工浏览路径，包括：

- 首页；
- 分类页；
- 正式知识详情页。

所有员工页面只能读取当前员工有权访问且已经正式发布的知识。查询必须先执行服务端受众过滤；草稿和未批准版本不得对员工可见。

## 3. 为什么现在做

- Task 9 已完成最终验收并进入 `DONE / codex`，Task 10 的直接依赖已经满足。
- Task 9 已完成 Django Admin 安全维护边界和幂等最小演示数据命令。
- 正式 `knowledge` App 已有服务端受众 Selector，可复用 `visible_articles` 和 `can_read_article` 的账号门槛、文章策略与 deny 优先语义。
- Task 9 最终正式工程回归为 `414 passed`，Django system check、迁移一致性检查和 Ruff 均通过。
- 正式员工 Django 首页、分类页和知识详情页尚未建立，员工读取能力还没有正式业务入口。

## 4. 已知现状

- `apps/knowledge/views.py` 当前只有模块入口说明，尚无正式员工页面 View。
- 正式根 `config/urls.py` 当前只包含 Admin、健康检查和本地开发模拟登录入口，尚未挂载 knowledge 员工路由。
- 当前没有 `apps/knowledge/urls.py`，也没有正式 `templates/knowledge/` 页面目录。
- `apps/knowledge/selectors.py` 已实现 `visible_articles` 和 `can_read_article`，员工读取遵循账号有效状态、文章受众策略和 deny 优先。
- Task 9 的 Article demo 保持 `N/A - SAFE STOP`：正式 KB 编号服务尚未实现，未创建 Article 样本，未伪造编号。
- Wagtail F08 的员工详情页仍位于 `experiments/wagtail_f08`，属于隔离 PoC，不能直接作为正式页面或正式 URL。
- 真实 `.env` 尚不存在；OpsAI PostgreSQL 容器、卷和数据库尚未创建或启动，未执行真实 `migrate`。
- 任务 8J 继续保持 `BLOCKED / unassigned`；PostgreSQL 持久环境核验不是 Task 10 当前开工的前置条件。

## 5. 依赖关系

- 直接依赖：Task 9——配置 Django Admin 和最小演示数据。
- 依赖状态：`DONE / codex`。
- 依赖是否满足：是。
- `tasks/TASKS.yaml` 没有为 Task 10 登记其他依赖。
- Task 11 依赖 Task 10，但 Task 11 继续保持 `BACKLOG / unassigned`，不得在 Task 10 中提前实现。

## 6. 后续实施允许范围

以下范围基于当前正式项目结构记录，仅在项目负责人允许进入页面实施阶段后使用；本次状态切换不修改这些业务文件：

- 正式员工页面 View：`apps/knowledge/views.py`；
- knowledge 正式路由：可按最小需要新增 `apps/knowledge/urls.py`；
- 正式根路由挂载：`config/urls.py`；
- 正式员工模板：可按最小需要新增 `templates/knowledge/` 下的首页、分类页和详情页模板；
- 服务端读取：优先直接复用 `apps/knowledge/selectors.py` 中的 `visible_articles` / `can_read_article`，只有页面查询确有必要时才增加少量读取封装；
- Task 10 直接测试：优先放入 `apps/knowledge/tests/`，只有跨 App 行为确有必要时才使用根 `tests/`；
- 必要的最小静态页面资源：`static/`；不得引入独立前端工程；
- 状态流转与验收明确要求的接力元数据文件。

任何超出以上范围的修改必须先说明原因并取得项目负责人授权。

## 7. 原则上禁止范围

Task 10 不包含以下工作：

- Task 11 的 P0 搜索、排序、高亮、筛选和搜索日志；
- Task 12 的 Article 创建、KB 编号、草稿编辑、版本保存、自动保存及 Wagtail 正式融合；
- Task 13 的提交审核、批准、驳回和发布事务；
- Task 15 的附件上传、私有存储和病毒扫描；
- Task 17 的钉钉免登、JSAPI、通讯录同步和真实钉钉联调；
- Task 19 的生产 Docker、Gunicorn、Caddy、备份和恢复配置；
- 真实 PostgreSQL 环境准备、真实 `.env`、真实 `migrate` 或持久数据操作；
- `experiments/wagtail_*` 的修改、复用或正式挂载；
- 新增或修改 migration；
- Article 假数据、硬编码 KB 编号、临时编号服务或任何绕过 Article 创建规则的方式。

## 8. 员工读取安全边界

- 首页、分类页和详情页的查询必须先执行服务端受众过滤，不能依赖前端隐藏。
- 无权限时不得泄露文章是否存在、标题、摘要或附件名。
- 草稿、未批准版本、未发布、下架或归档内容不得进入员工正式页面。
- `ArticleAudience` 的 deny 继续优先于 allow。
- 账号失效或不满足员工读取门槛时拒绝访问。
- `is_staff`、`is_superuser`、编辑员、审核员、知识库管理员、文章作者或 Space 负责人身份都不自动获得员工读取权限。
- 页面模板必须保持自动转义；如展示普通文本换行，应使用安全的模板表达，不把内容当作可执行 HTML。
- 员工页面响应和缓存策略不得造成跨用户内容泄露。

## 9. Wagtail 边界

Wagtail 继续保留在 `experiments/wagtail_*` 隔离 PoC 中。Task 10 不得：

- 把 Wagtail 加入正式根依赖；
- 修改正式 `INSTALLED_APPS` 接入 Wagtail；
- 正式挂载 Wagtail URL；
- 修改正式内容模型完成 Wagtail 切换；
- 直接复制实验 URL、View、模板或合成配置作为正式入口。

如果正式员工页面必须依赖 Wagtail 才能实现，应停止并报告，不得自行扩大范围。

## 10. Article 与 KB 编号边界

Task 10 是员工读取路径，不是文章创建路径。不得为了页面展示实现 KB 编号服务、硬编码 KB 编号、创建 Article 假数据或绕过 Article 创建规则。Article demo 继续保持 `N/A - SAFE STOP`。

## 11. PostgreSQL 与敏感配置边界

Task 10 当前没有 PostgreSQL、真实 `.env` 或持久数据库前置要求。本任务不得自动读取 `OpsAI.env`、创建真实 `.env`、启动 PostgreSQL、创建容器或卷、执行真实 `migrate` 或访问持久数据。

如果后续实施发现必须进行真实数据库验证，应停止对应部分并单独申请授权。任务 8J 继续保持 `BLOCKED / unassigned`。

## 12. 验收标准

- [ ] 首页、分类页和详情页在 PC 与手机上可用。
- [ ] 所有查询先执行服务端受众过滤。
- [ ] 无权限时不泄露文章存在性、标题、摘要或附件名。
- [ ] 草稿和未批准版本不可见。
- [ ] 未发布、下架和归档内容不可见。
- [ ] 正式页面不复用实验 URL 作为生产入口。
- [ ] 页面请求测试覆盖匿名、失效账号、无受众、deny、下架、草稿隔离和响应缓存。
- [ ] 浏览器响应式与模板自动转义验收通过。
- [ ] 正式工程必要回归、Django system check、迁移一致性检查和 Ruff 通过。

## 13. 验证计划

进入页面实施阶段后，至少验证：

1. 首页、分类页和详情页的正常读取路径；
2. 匿名、失效账号、无受众、显式 deny、不存在、未发布、下架和归档场景；
3. 草稿、工作版本和未批准版本不会泄露；
4. 员工读取不因系统操作角色、作者或 Space 负责人身份绕过；
5. PC 与手机响应式布局、模板自动转义和缓存边界；
6. 正式 Django 工程相关自动测试与必要回归；
7. Django system check、`makemigrations --check --dry-run` 和 Ruff。

本次开工状态切换不运行页面测试，也不把 Task 9 的历史测试冒充为 Task 10 实施结果。

## 14. 本次状态切换边界

- 只更新 `tasks/TASKS.yaml`、`tasks/CURRENT_TASK.md`、`docs/PROJECT_STATE.md` 和 `docs/HANDOFF.md`。
- 不修改 `apps/`、`templates/`、`static/`、`config/`、`tests/`、`experiments/`、`migrations/`、`deploy/` 或 `pyproject.toml`。
- 不创建 Commit，不 Push，不启动数据库，不开始页面开发。
- 状态切换完成并经项目负责人验收后，再按后续明确指令进入 Task 10 页面实施。

## 15. 状态流转

### BACKLOG

历史状态。Task 9 完成后，Task 10 的依赖已满足，但尚未获得正式开工授权。

### IN_PROGRESS

当前状态。项目负责人已正式选择 Task 10，并授权 `BACKLOG → IN_PROGRESS`，负责人为 `codex`。当前只完成开工状态与接力元数据同步，页面业务代码尚未开始。

### VERIFY

只有 Task 10 实施、验证和必要状态文档同步完成后，才可由后续明确授权进入。

### DONE

只有验收条件满足、实际验证证据完整并经项目负责人最终验收后，才可进入。

### BLOCKED

只有出现真实阻断条件且当前无法继续时才能使用，并必须记录阻塞原因和解除条件。

### HANDOFF

只有发生真实 Agent、人员或电脑切换且任务仍未完成时才使用。当前由 Codex 连续执行，不构成交接。

## 16. 当前备注

- 当前唯一 `IN_PROGRESS` 任务为 Task 10，负责人为 `codex`。
- Task 9 保持 `DONE / codex`。
- 任务 8J 保持 `BLOCKED / unassigned`。
- Task 11 及后续业务任务保持 `BACKLOG / unassigned`。
- 当前仍无待处理 AI 交接。
- 本轮未开始首页、分类页或正式知识详情页开发。
