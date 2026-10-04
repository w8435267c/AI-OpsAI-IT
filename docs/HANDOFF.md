# OpsAI AI Handoff

> 当前无待处理 AI 交接。

## 1. 当前交接状态

当前没有真实的 Agent 切换事件，也不存在需要下一位 Agent 接续的中断现场。Task 11A、11B 已完成并双端同步，业务实现与项目负责人视觉验收均已完成；Task 11“开发 P0 搜索”当前为 `VERIFY / codex`，仍由 Codex 连续执行，因此不构成 Agent 间交接。

| 项目 | 当前值 |
| --- | --- |
| 当前任务 | `11` - 开发 P0 搜索 |
| 任务状态 | `VERIFY` |
| 负责人 | `codex` |
| 开工日期 | `2026-10-04` |
| 依赖 | 任务 `10`，状态为 `DONE / codex` |
| 范围冻结 Commit | `5266c278803b16a3c0ec4a0eaffdcb16d641580c`，已双端同步 |
| 业务实施状态 | Task 11A、11B 已完成并双端同步；V1 必须业务功能与负责人视觉验收已完成，不需要 Task 11C |
| 当前等待动作 | PostgreSQL 专项验证完成并 PASS，或项目负责人明确接受分阶段验收 |
| 当前禁止动作 | 不把 Task 11 改为 DONE，不开始 Task 11C 或 Task 12，不扩大标签、别名、日志模型、PostgreSQL、Wagtail 或 Article 创建范围 |
| Agent 切换状态 | 未发生 |

Task 11 V1 只搜索 `current_published_version.title`、`summary` 和 `body_plaintext`，必须先通过 `employee_visible_articles` 完成权限过滤，再搜索、统计、排序和分页；草稿、历史版本、全库匹配总数和无权限内容不得进入员工搜索。搜索或点击日志如需新增 Model / Migration，必须先提出 `SCOPE QUESTION`；PostgreSQL 操作当前未授权，8J 保持 `BLOCKED / unassigned`。

Task 11 实施与验收证据：

| 阶段 | Commit | 标题 | 状态 |
| --- | --- | --- | --- |
| 11A | `6240147054f909c9f88c14d67e99f7c55ccc83d1` | `feat(search): add secure employee article search reader` | `DONE / SYNCED` |
| 11B | `7ac5cd894db052dc3c7eb7e2721dbcc4f34d7ea6` | `feat(search): add employee search results page` | `DONE / SYNCED` |

Task 11A 专项为 `13 passed / 16 subtests`，Task 11B 专项为 `13 passed / 11 subtests`，knowledge 回归为 `310 passed / 59 subtests`，正式工程回归为 `486 passed / 102 subtests`。Reader 在 3 条和 23 条结果时均为 1 query，搜索页面在 3 条和 23 条结果时均为 4 queries，无 N+1。

项目负责人视觉验收 PASS：网络搜索 21 条并按 20+1 分页，打印机搜索 1 条，不存在关键词和 Draft-only 关键词均为 0 条，隐藏知识未泄露，KB-910001 正式详情链路及桌面、手机页面均通过。当前唯一剩余正式验证项是 PostgreSQL 下当前 V1 ORM 查询、中文 substring、确定性排序、`NULLS LAST`、查询计划、索引利用和典型数据量性能；当前 V1 不要求改为 PostgreSQL FTS。

上一任务 Task 10 的内部阶段和双端同步证据如下：

| 阶段 | Commit | 标题 | 状态 |
| --- | --- | --- | --- |
| 10A | `cf8bf1ff1692dedd69e5fbf97f0632a460d66c0b` | `feat(knowledge): add formal employee knowledge readers` | `DONE / SYNCED` |
| 10B | `9721e2817135a4e6002d9a2d39e151fdc480b8f7` | `feat(knowledge): add secure employee knowledge home` | `DONE / SYNCED` |
| 10C | `8435b4255e459ede018bee2dc6771caf89b6c76e` | `feat(knowledge): add audience-filtered category pages` | `DONE / SYNCED` |
| 10D | `5fb5c1f9cedd6a347e1f240cb41d404b84125dec` | `feat(knowledge): add secure published article detail page` | `DONE / SYNCED` |
| 10E | `807028ef3d5c2092fa679c811128acd3c07a30fc` | `test(knowledge): harden employee page final regression` | `DONE / SYNCED` |

Task 10 最终验证为页面专项 `30 passed`、knowledge `310 passed`、正式工程回归 `460 passed`；Django check、迁移一致性检查、Ruff、format 和 diff 检查通过。Desktop `1440 × 900` 与 Mobile `390 × 844` 浏览器验收通过，无异常 N+1。Task 10 V1 正式前端为 Django Templates + 项目自有 `static/css/opsai.css`，Bootstrap / HTMX 为 `NOT REQUIRED FOR TASK 10 V1`。

项目负责人最终人工视觉验收为 PASS：首页、分类页、知识详情、返回链路、无权限 404、隐藏知识隔离和 Draft 隔离均通过；员工首页、“电脑故障”分类、KB-900001 正式详情和 Published A 均正常，Draft B、隐藏分类及 KB-900003 无权限内容未泄露，KB-900003 返回统一员工侧 404。临时 8765 服务、`visual.sqlite3` 与验收目录已清理，8000 服务未受影响，正式数据库未操作。

因此，当前不存在真实的“上一执行 Agent → 下一建议 Agent”业务交接记录。本节不填写不存在的上一执行 Agent、交接时间或接管现场，也不把 DONE 状态同步伪装成新的 Agent 交接事件。

## 2. 文档职责与边界

`docs/HANDOFF.md` 只回答：正在进行中的任务如果必须中断，下一位 Agent 需要知道哪些现场事实、应如何安全接续。

- `docs/PROJECT.md`：说明项目是什么、长期范围和技术路线。
- `docs/PROJECT_STATE.md`：说明项目当前总体做到哪里及已有验证证据。
- `tasks/TASKS.yaml`：登记任务池、依赖和任务状态。
- `tasks/CURRENT_TASK.md`：定义当前唯一允许做什么。
- `docs/HANDOFF.md`：记录当前任务做到哪里，以及如何交给下一位 Agent。

没有真实切换、中断或接管需求时，本文件保持“当前无待处理 AI 交接”，不得为了日常更新制造交接历史。

## 3. 何时建立真实交接记录

出现以下任一情况，并且当前任务尚未完成时，应使用第 4 节模板建立真实交接记录：

- 当前 Agent 额度耗尽或无法继续；
- Codex、Qoder CN、Claude Code 或其他 Agent 之间切换；
- 更换电脑或执行环境；
- 当前任务遇到阻塞，需要其他 Agent 接手；
- 会话即将结束，任务做到一半必须中断；
- 项目负责人要求切换执行端或执行者。

交接记录必须填写真实 Agent 名称、真实时间、完整 Git 哈希、实际 Commit、实际文件现场、已执行的命令和真实结果。不得用“大概”“应该”“可能”“估计”代替可核验事实；未执行的检查必须明确写“未执行”。

## 4. 正式交接模板

复制以下模板建立真实交接记录。所有字段均必须填写；不适用时写“不适用”，没有内容时写“无”，工作区干净时明确写“工作区干净”，不得留空。

### 4.1 基本信息

1. **项目：** `<填写项目名称与实际仓库路径>`
2. **当前任务编号：** `<与 tasks/CURRENT_TASK.md 和 tasks/TASKS.yaml 一致的编号>`
3. **当前任务名称：** `<填写完整任务名称>`
4. **上一执行 Agent：** `<填写真实 Agent 名称，不得虚构>`
5. **下一建议 Agent：** `<填写真实建议对象；尚未确定时明确写“未指定”，不得猜测>`
6. **交接时间：** `<填写含时区的真实时间，例如 YYYY-MM-DD HH:mm:ss +08:00>`
7. **当前状态：** `<填写 READY / IN_PROGRESS / VERIFY / BLOCKED / HANDOFF 等真实状态，并说明依据>`

### 4.2 本轮工作

8. **本轮目标：** `<填写本轮获授权的目标和明确边界>`
9. **已完成：** `<逐项填写已完成工作及可核验证据；没有则写“无”>`
10. **未完成：** `<逐项填写剩余工作；没有则写“无”>`
11. **当前问题：** `<填写阻塞、风险、错误现象和解除条件；没有则写“无”>`

### 4.3 文件现场

12. **修改文件：**
    - 已提交修改：`<列出文件及对应完整 Commit 哈希；没有则写“无”>`
    - 未提交修改：`<列出已跟踪文件及修改性质；工作区干净则写“工作区干净”>`
    - 修改范围说明：`<说明每个文件为什么修改，不得遗漏或混入任务外文件>`
13. **未跟踪文件：** `<逐项列出 git status 中的未跟踪文件；没有则写“无”>`

### 4.4 Git 现场

14. **当前分支：** `<填写完整分支名>`
15. **当前 HEAD：** `<填写 40 位完整 Commit 哈希>`
16. **本轮 Commit：** `<逐项填写完整哈希和完整标题；未创建则写“无”>`
17. **GitHub 推送状态：** `<填写“已同步 / 未同步 / 未验证”；已实时核验时附目标分支和 40 位完整哈希>`
18. **Gitee 推送状态：** `<填写“已同步 / 未同步 / 未验证”；已实时核验时附目标分支和 40 位完整哈希>`

不能只写“已推送”。“已同步”必须有实时远端查询证据；没有查询就写“未验证”。

### 4.5 验证现场

19. **验证命令：** `<按实际执行顺序逐条填写可复现的完整命令和运行目录；未执行则写“未执行”>`
20. **测试结果：** `<逐条对应命令填写真实结果，例如“386 passed”；失败或未执行必须如实记录>`

### 4.6 运行环境与数据风险

21. **Docker/服务状态：**
    - 是否启动：`<是 / 否 / 不适用>`
    - 容器名称：`<逐项列出；没有则写“无”>`
    - 服务状态：`<运行、停止、异常或不适用，并附核验方式>`
    - 数据卷：`<名称和是否由本轮创建；没有则写“无”>`
    - 是否需要停止：`<是 / 否 / 不适用，并说明原因>`
22. **是否涉及 migration：** `<是 / 否>`
    - 若为“是”：填写 migration 文件、是否已应用、应用环境和回滚风险。
23. **是否涉及数据库写入：** `<是 / 否>`
    - 若为“是”：填写写入对象、测试数据库 / 开发数据库 / 其他环境，以及是否可回滚和安全回滚方法。
24. **是否涉及敏感配置：** `<是 / 否>`
    - 只记录变量名、是否必需、是否存在、是否被 Git 跟踪或忽略，以及安全配置方式。
    - 可以写“需要 `.env`”，严禁记录或复制 `.env` 正文、`SECRET_KEY` 实际值、数据库密码、API Key、Token、Cookie、私钥或账号密码。

### 4.7 回滚与下一步

25. **回滚方式：**
    - 代码回退：`<优先填写基于明确 Commit 的 revert 或经确认的具体文件恢复方式>`
    - 工作区恢复：`<逐文件说明如何安全保留或恢复未提交工作>`
    - 数据库回滚：`<说明是否涉及及风险；不涉及则写“不适用”>`
    - Docker 资源：`<说明容器、网络、卷的影响和处理要求；不涉及则写“不适用”>`
    - 不得建议 `git reset --hard`、`git clean -fd`、force push 或其他破坏历史及未知现场的操作。
26. **下一步建议：** `<填写下一项最小、安全、已获授权或需负责人确认的动作>`
27. **下一 Agent 开工必读文件：**
    1. `AGENTS.md`
    2. `docs/PROJECT.md`
    3. `docs/PROJECT_STATE.md`
    4. `docs/HANDOFF.md`
    5. `tasks/TASKS.yaml`
    6. `tasks/CURRENT_TASK.md`
28. **下一 Agent 应首先执行的检查：**

    在实际仓库根目录依次执行：

    ```powershell
    git status --short --untracked-files=all
    git branch --show-current
    git rev-parse HEAD
    git log --oneline -10
    ```

    然后核对实际 HEAD、HANDOFF 记录的 HEAD、`tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml` 和工作区现场。任一项不一致时立即停止，不继续开发，不自行 restore、stash、reset、clean、merge 或 rebase；应保留现场并向项目负责人报告差异。

## 5. 交接证据规则

### 5.1 Git 证据

- 分支必须写完整名称，HEAD 和已核验远端 HEAD 必须写 40 位完整哈希。
- 本轮 Commit 必须同时记录完整哈希和标题；没有 Commit 时明确写“无”。
- GitHub 与 Gitee 分别记录“已同步 / 未同步 / 未验证”。远端推送命令成功但尚未实时查询时，不能写“已同步”。
- 已提交修改、未提交修改和未跟踪文件必须分开记录，并与 `git status --short --untracked-files=all` 一致。

### 5.2 测试与验证证据

- 每项结果必须能对应到实际执行的命令、运行目录和真实输出。
- 不得只写“测试通过”；应写明例如“命令：`...`；结果：`386 passed`”。
- 未运行的测试、Django check、迁移检查或静态检查必须明确写“未执行”及原因，不得引用其他任务的历史结果冒充本轮结果。

### 5.3 Docker、服务与持久数据证据

- 涉及 Docker、PostgreSQL、Web 服务或 Worker 时，必须记录是否启动、容器名称、服务状态、数据卷和是否需要停止。
- 不涉及时明确写“不适用”，不得留空。
- migration 为“是”时，必须记录文件、应用状态、应用环境和回滚风险。
- 数据库写入为“是”时，必须记录写入对象、环境和可回滚性，不得读取或记录真实凭据。

### 5.4 敏感信息保护

交接记录严禁出现真实 `SECRET_KEY`、数据库密码、API Key、Token、Cookie、私钥、账号密码或 `.env` 正文。需要配置时只说明变量名、状态和安全来源，不记录实际值。

### 5.5 安全回滚

回滚说明必须分别覆盖代码、未提交工作区、数据库和 Docker 资源。代码优先基于可核验 Commit 使用安全的 revert，或在明确目标并保留用户改动的前提下逐文件恢复；不得用破坏性命令掩盖未知修改或改写远端历史。

## 6. 下一 Agent 开工流程

1. 按第 4 节第 27 项顺序完整读取六个接力文件。
2. 在仓库根目录执行第 28 项四条 Git 检查命令。
3. 对照真实交接记录核对 HEAD、当前任务、任务登记、工作区、Commit、远端与验证证据。
4. 只有现场一致且项目负责人已经授权当前任务时，才查看相关代码、运行安全验证并继续唯一当前任务。
5. 发现任何不一致、未知修改、状态冲突或权限缺口时，立即停止扩展实施，保留现场并报告；不得自行清理、恢复或改写历史。

## 7. 当前备注

- Task `10` 当前状态为 `DONE`，负责人为 `codex`；10A～10E 已完成并双端同步，项目负责人最终人工视觉验收为 PASS。
- Task 9 保持 `DONE / codex`；Task 10 的直接依赖已经满足。
- Task 10 正式员工首页、分类页、知识详情页及返回链已完成；安全、缓存、自动转义、响应式和性能验收通过。
- 正式员工读取来源为 `current_published_version`；列表 Reader 为 `employee_visible_articles`，详情 Reader 为 `get_employee_article_detail`；V1 正文使用 `body_plaintext → body_text`。
- Task 10 V1 正式前端为 Django Templates + 项目自有 CSS；Bootstrap / HTMX 当前不要求接入。
- Task 11A、11B 已完成并双端同步，项目负责人视觉验收 PASS；Task 11 当前为 `VERIFY / codex`，业务实现完成，不需要 Task 11C，剩余 PostgreSQL 专项验证。
- 当前没有真实 Agent 切换，所以没有上一执行 Agent、下一建议 Agent、交接时间或未完成业务现场可记录。
- 任务 8J 保持 `BLOCKED / unassigned`；Task 12 及后续业务任务保持 `BACKLOG / unassigned`。
- 如后续发生真实 Agent 切换，下一 Agent 必须先读取 Task 11 已冻结范围，不得自行扩大标签、别名、日志模型、PostgreSQL、Wagtail 或 Article 创建范围。
- 本文件保留统一交接规则和模板，并与 `tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml` 的 `VERIFY` 状态保持一致。
