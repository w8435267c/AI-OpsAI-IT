# OpsAI Current Task

> Task 10 的 10A～10E 已全部完成并双端同步，项目负责人最终人工视觉验收为 PASS，当前状态为 `DONE / codex`；当前没有新的 `IN_PROGRESS` 或 `VERIFY` 任务。

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `10` |
| 任务名称 | 开发首页、分类页和正式知识详情页 |
| 优先级 | `MUST` |
| 当前状态 | `DONE` |
| 当前负责人 | `codex` |
| 开工日期 | `2026-09-30` |
| 进入 VERIFY | `2026-10-03` |
| 完成日期 | `2026-10-04` |
| 直接依赖 | Task 9，`DONE / codex` |
| 最终业务 Commit | `807028ef3d5c2092fa679c811128acd3c07a30fc` |
| VERIFY 状态 Commit | `713bb150d40bcf39cfcaf3be54d6e12a74e68a2e` |
| 双端同步 | GitHub、Gitee 与本地业务 HEAD 已一致 |

Task 10 的开发、自动测试、安全检查、性能回归、浏览器视觉验收和项目负责人最终人工验收均已完成。Task 10 已正式封板，不再修改其业务代码；下一任务尚未正式授权，Task 11 保持 `BACKLOG / unassigned`。

## 2. 内部阶段与 Commit

| 阶段 | 状态 | Commit | 标题 |
| --- | --- | --- | --- |
| 10A | `DONE / SYNCED` | `cf8bf1ff1692dedd69e5fbf97f0632a460d66c0b` | `feat(knowledge): add formal employee knowledge readers` |
| 10B | `DONE / SYNCED` | `9721e2817135a4e6002d9a2d39e151fdc480b8f7` | `feat(knowledge): add secure employee knowledge home` |
| 10C | `DONE / SYNCED` | `8435b4255e459ede018bee2dc6771caf89b6c76e` | `feat(knowledge): add audience-filtered category pages` |
| 10D | `DONE / SYNCED` | `5fb5c1f9cedd6a347e1f240cb41d404b84125dec` | `feat(knowledge): add secure published article detail page` |
| 10E | `DONE / SYNCED` | `807028ef3d5c2092fa679c811128acd3c07a30fc` | `test(knowledge): harden employee page final regression` |

## 3. 已完成能力

1. 员工正式首页 `/` 已可用，只展示当前员工有权查看的正式知识。
2. 首页分类由当前员工可见知识反向推导，不展示只有不可见内容的分类。
3. 分类页 `/categories/<category_id>/` 先执行服务端受众过滤，再统计和分页。
4. 正式知识详情页 `/kb/<kb_no>/` 使用 KB 编号，不把 Article 内部 UUID 暴露为员工文章 URL。
5. 不存在、无权限、DENY、未发布、下架、归档和未来生效的知识不会向员工泄露。
6. `current_published_version` 是正式员工读取来源，草稿和 `latest_working_version` 不会覆盖正式页面。
7. 首页、分类、详情以及返回分类、返回首页的浏览链已在桌面和手机完成验收。

## 4. 正式读取与正文契约

- 列表 Reader：`employee_visible_articles`。
- 详情 Reader：`get_employee_article_detail`。
- 正式版本来源：`current_published_version`。
- 权威结构化正文：`ArticleVersion.body`。
- Task 10 V1 员工正文：`body_plaintext → body_text` 的安全普通文本投影。
- 员工页面不直接渲染未知 `body` JSON，不使用 `safe`、`mark_safe` 或 `autoescape off`。

## 5. 安全结论

- 匿名、inactive、disabled、departed 账号访问员工页面返回 `401`。
- 不存在、无权限、DENY、未发布等详情返回统一且不泄露存在性的员工侧 `404`。
- 首页、分类、详情的 `200 / 401 / 404 / 405` 契约均使用 `Cache-Control: private, no-store`。
- `<script>`、`<b>`、`<img onerror>` 等外观内容只作为普通文本显示，不执行脚本或产生 HTML 元素效果。
- `is_staff`、`is_superuser`、系统操作角色、作者和 Space 负责人身份都不自动绕过员工受众权限。

## 6. 前端资源决策

Task 10 V1 的正式前端基线为：

```text
Django Templates
+
项目自有 static/css/opsai.css
```

Bootstrap / HTMX 为 `NOT REQUIRED FOR TASK 10 V1`：当前页面没有必须依赖 HTMX 的动态交互，自有 CSS 已通过桌面和手机验收，仓库也不存在可信固定版本的本地资源。后续如有真实需求，只能按可信来源、固定版本、本地 vendor 的方式单独引入。

## 7. 验证证据

- 页面专项：`30 passed`。
- knowledge：`310 passed`。
- 正式工程回归：`460 passed`。
- Django system check：PASS。
- Migration check：`No changes detected`。
- Ruff：PASS。
- Format：PASS。
- `git diff --check`：PASS。
- Desktop：`1440 × 900`，首页、分类、详情 PASS，无横向溢出。
- Mobile：`390 × 844`，首页、分类、详情 PASS，无横向溢出，分页和返回链接正常。
- 性能：首页 3 篇与 23 篇均为 4 queries；分类 3 篇与 23 篇均为 5 queries；详情为 3 queries；无异常 N+1。
- Owner Visual Acceptance：PASS；员工首页、“电脑故障”分类、KB-900001 正式详情和 Published A 正常，Draft B、隐藏分类及 KB-900003 无权限内容未泄露，统一员工侧 404 符合预期。
- 临时验收环境：8765 服务、`visual.sqlite3` 与临时目录已清理，8000 服务未受影响；未读取真实 `.env`，未操作 PostgreSQL。

## 8. 当前边界与下一步

- Task 10：`DONE / codex`，项目负责人最终人工视觉验收 PASS。
- 当前：没有新的 `IN_PROGRESS` 或 `VERIFY` 任务；下一任务尚未正式授权。
- Task 11：保持 `BACKLOG / unassigned`，未授权开始搜索开发。
- Task 8J：保持 `BLOCKED / unassigned`；真实 PostgreSQL / `.env` 环境验证尚未授权完成。
- 不读取 `OpsAI.env`，不创建真实 `.env`，不启动 PostgreSQL，不执行真实 `migrate`。
- 不实现 Article 创建、KB 编号服务、审核发布、附件、钉钉或 Wagtail 正式融合。
- 不得修改 Task 10 封板状态，也不得把 Task 11 改为 `READY`、`ASSIGNED` 或 `IN_PROGRESS`。

## 9. 状态流转

### IN_PROGRESS

历史状态。Task 10 的 10A～10E 已完成并双端同步。

### VERIFY

历史状态。开发与验证证据齐备后，项目负责人已完成最终人工验收并授权封板。

### DONE

当前状态。项目负责人最终人工视觉验收为 PASS，Task 10 已正式封板为 `DONE / codex`。
