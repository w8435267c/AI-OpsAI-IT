# Task 12E 管理端知识编辑链验收

## 1. 验收结论

Task 12E 已完成并通过验收，状态为 `DONE / ACCEPTED`，验收等级为 `PASS_WITH_VISUAL_FINDINGS`。

- P0：0
- P1：0
- P2：0
- P3：2（均为非阻塞视觉遗留）
- Task 12E 自身上线阻塞：无 P0 / P1 / P2 阻塞

该结论只覆盖 Task 12E 管理端知识编辑链，不代表整个 OpsAI 项目已具备上线条件。Task 13 仍为 `BACKLOG / unassigned`，任务 8J 仍为 `BLOCKED / unassigned`。

## 2. 完成范围

Task 12E 最终覆盖以下能力：

1. 管理端知识列表；
2. 新建 Article；
3. Draft 编辑器；
4. Autosave；
5. Manual Save；
6. History；
7. History Detail；
8. Restore；
9. Draft Preview；
10. 管理端与员工端权限隔离；
11. 乐观锁 / CAS；
12. Employee Published-only 隔离；
13. 真实 Chromium 浏览器主链验收。

## 3. 自动化验收证据

以下结果是 Task 12E-08 及此前阶段累计形成的正式自动化验收证据，不是 Task 12E-09A 重新执行的结果：

| 检查 | 结果 |
| --- | --- |
| `pytest apps tests` | 717 passed、9 skipped、571 subtests、0 failed |
| Django system check | PASS |
| `makemigrations --check --dry-run` | No changes detected |
| Ruff | PASS |
| Format | PASS |
| `git diff --check` | PASS |
| `node --check` | PASS |

9 个 skipped 项为现有 SQLite test settings 下的 PostgreSQL 专项，不代表测试失败。

## 4. Task 12E-09A 真实浏览器验收

### 4.1 环境边界

- 使用仓库外 acceptance settings 与独立 SQLite 数据库；
- 未读取真实 `.env`；
- 未操作 Docker；
- 未连接 PostgreSQL；
- 使用真实 Chromium 页面完成验收；
- 原始截图、隔离 SQLite 与辅助验收文件保存在仓库外 `Task12E09A` 验收目录，不是项目运行依赖，也未提交 Git。

### 4.2 主链结果

以下功能链全部 PASS：

- Manage List；
- Create；
- Edit；
- Autosave；
- Manual Save；
- History List；
- History Detail；
- Restore；
- Restore 后 Autosave；
- Dirty → Preview；
- Preview → Edit；
- Employee 权限隔离；
- Employee Search 隔离；
- 双标签 CAS 冲突。

关键网络证据：

- Create：`POST → 303 → Edit`；
- Autosave：HTTP 200，token `1 → 2`；
- Manual Save：HTTP 200；
- Restore：`POST → 303`；
- Dirty Preview：Autosave HTTP 200 后 Preview GET 200；
- Employee 管理入口返回 403，员工详情及绕过查询参数返回 404；
- 双标签冲突中，A Autosave 返回 200，B 使用旧 token Autosave 返回 409。

浏览器 Console 为 0 error。`favicon.ico` 404 属于非核心浏览器噪声，不影响 CSS、JavaScript 或页面功能，不登记为 P2。

### 4.3 版本链真实证据

Create 完成后进入 Edit。首次 Autosave 将 lock token 从 1 推进到 2。

Manual Save 的版本链为：

```text
v1 DRAFT
→ v1 SAVED
→ v2 DRAFT
```

Manual Save 后生成新的 Draft ID，新 token 为 1，`change_summary` 为“基于已保存版本 v1 继续编辑”。

Restore 使用 `v1 SAVED` 作为来源，先保存当前 Draft，再创建新的 `v3 DRAFT`；`change_summary` 为“从版本 v1 恢复”。来源历史未被修改。

Dirty Preview 会先完成 Autosave，再发起 Preview GET；Preview 显示服务器已保存的最新草稿内容。

## 5. 双标签 CAS 证据

真实双标签验证已完成：A、B 同时持有 token 3。

1. A Autosave 成功，token `3 → 4`；
2. B 使用旧 token 3 Autosave，服务器返回 409；
3. B 页面进入 `blocked` 状态；
4. Manual Save 与 Preview 被禁用，Reload 入口显示；
5. Reload 后可见 A 保存的内容和 token 4。

结论：没有发生 last-write-wins，旧窗口没有覆盖新内容。

## 6. Employee Published-only 隔离

对未发布 Article 的真实浏览器验证结果：

- Manage Preview：200；
- Employee Detail：404；
- Employee Search：0 结果；
- `?preview=1`、`?draft=1`、`?include_draft=1` 均不能绕过员工读取限制。

结论：Working Draft 没有泄漏至 Employee Published-only 读取链。

## 7. P3 视觉遗留

### P3-UI-01：Create 表单视觉一致性

Create 表单视觉样式偏原生，字段宽度、Label 与帮助文字排布和 Edit 页风格不完全一致。

影响：不阻塞创建，无数据风险、权限风险或功能阻塞。

处理：进入管理端 UI 统一精修 Backlog，本轮不修复。

### P3-UI-02：Edit 操作按钮层级

Edit 页的“预览草稿”和“保存版本并继续编辑”当前使用相同的主按钮视觉，主次层级不够明显。

影响：两个操作均可正常点击，无误操作阻塞，无功能或安全风险。

处理：进入管理端 UI 统一精修 Backlog，本轮不修复。

## 8. 未执行与明确边界

- 窄屏验收：`NOT_EXECUTED_BROWSER_CAPABILITY`。浏览器能力未实际应用 `390 × 844` 视口，因此不得宣称 Task 12E 移动端视觉验收 PASS。
- 正式 PostgreSQL：本次浏览器验收未连接；Task 12D 的临时 PostgreSQL 专项也不等于 8J 持久 PostgreSQL 验收。
- Task 13：未开始。本轮未实现提交审核、审核通过、审核驳回、发布、重新发布、审核流 UI 或审核工作台。
- 生产与完整上线：未验证，不因 Task 12E 完成而改变。

## 9. 最终状态

| 项目 | 状态 |
| --- | --- |
| Task 12E-09A | `PASS_WITH_VISUAL_FINDINGS` |
| Task 12E | `DONE / ACCEPTED` |
| Task 12 | `IN_PROGRESS / codex` |
| Task 13 | `BACKLOG / unassigned` |
| 8J | `BLOCKED / unassigned` |
| P3 UI | `BACKLOG / non-blocking` |
