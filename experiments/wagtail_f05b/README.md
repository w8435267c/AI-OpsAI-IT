# F05B 最终验收：A，实验审核发布闭环通过

F05B-4（2026-09-13）完成真实 HTTP 发布异常回滚及阶段收尾。没有发现需要修改业务实现的缺陷；本轮仅补测试、runner 和报告。

**F05B 已完成实验环境中的审核发布闭环；尚未接入正式业务读取、员工受众及正式角色内容权限，未验证 PostgreSQL、并发、永久历史保留或浏览器交互。**

## 阶段完成情况

| 能力 | 已验证的实验行为 |
| --- | --- |
| 批准资格 | 服务每次重读有效账号、实际审核组、任务和修订关联；失效、缺失、错绑均拒绝 |
| TaskSubmission | 首次提交和驳回重提均与原生任务创建同事务记录实际提交人；按 TaskState 唯一绑定受审修订，旧身份不覆盖 |
| 禁止自审 | 受审修订创建者与当轮提交人均拒绝，超级管理员和通用发布权限不绕过 |
| 批准与发布 | approve_review 调用原生 TaskState.approve → WorkflowState.update/finish → F05B 完成回调；只发布该任务受审 Revision 一次 |
| HTTP 入口 | 任务表单、认证、账号状态、POST、CSRF、字段白名单；actor 来自 request.user，实际执行仍调用同一服务 |
| HTTP 旁路 | 本实验原生 action、编辑发布 action、相关批量入口及原限制操作保持关闭；预期拒绝返回中文及 400/403/409/405 等适当状态 |
| 原配置兼容 | F05A 不注册 F05B 按钮/路由，新服务仍拒绝，原提交/重提及完成保护正常 |

正式目标取自 TaskState.revision，并核对 TaskSubmission 及内容归属，不接受外部指定发布修订，不以最新草稿替代。批准检查、状态转换和发布处于服务外层 atomic 内；异常回滚仅按顺序请求验证，不宣称并发安全。

## 新增 HTTP 回滚证据

新增 `ApprovalHTTPTests.test_http_publish_failure_rolls_back_then_retry_once`，复用既有夹具和 PublishRevisionAction._publish_revision 注入位置：

1. 合格审核员真实登录，GET 审核页返回 200，携有效 CSRF 令牌向已有批准 URL 发起真实 POST。
2. spy 委托实际 approve_review，验证任务 ID 和认证用户正确，调用一次。发布前注入点重新查询数据库：TaskState 与 WorkflowState 均已为 approved，finished_by 为审核员且完成时间非空；传入发布动作的 Revision 就是受审 V2，正式指针此时仍为 V1。
3. 抛出非预期 RuntimeError，由测试客户端捕获。没有修改视图或服务去吞异常，没有返回虚假成功。
4. 异常后重新查询并比较 KnowledgeContent、Revision、ModelLogEntry、WorkflowState、TaskState、TaskSubmission、Article、ArticleVersion、ReviewRecord 全字段快照，与请求前完全一致。任务/工作流恢复 in_progress，正式 V1 仍可读取。
5. 移除注入后向同一 URL、同一任务重新 POST，返回批准成功，任务/工作流为 approved，live_revision 准确为 V2，正式读取 V2，仅新增一条 V2 发布日志。
6. 再次提交同一批准请求返回 409 中文任务反馈，快照不变，不增加发布记录。旧业务数据和既有修订由公共 tearDown 再次核验不变。

该注入点位于发布底层操作执行前，证明真实 HTTP 路径中的已写审核状态和相关记录随服务事务回滚；不将此表述为覆盖所有可能的发布中途故障位置。

## 本轮实际运行与检查

| 执行命令模式 | 实际收集范围 | 数量 | 结果 |
| --- | --- | ---: | --- |
| stage，执行 1 次 | tests：资格/提交身份 20；test_services：服务 9；test_http：HTTP 12（含新增回滚） | 41 | 全部通过，8.833 秒 |
| compat，执行 1 次 | test_compat 2；F05A 原提交/重提及原关闭动作保护 2 | 4 | 全部通过，1.163 秒 |

**共 2 次 runner 执行、45 次测试执行、45 个不重复测试方法**，两组测试 ID 不重叠。新增 HTTP 测试已在 stage 中执行一次，未再单独运行；subTest 不另计。没有将历史次数累计到本轮，没有运行整个项目或所有历史实验。

- stage 在独立 F05B 合成配置下执行 `makemigrations(check=True, dry_run=True)`：No changes detected，无文件生成。
- 两个 runner 都执行 Django 系统检查，无错误；SQLite 表/字段注释警告保留，compat 实际报告 108 条、0 silenced。未修改 SILENCED_SYSTEM_CHECKS，也未关闭迁移。
- 既有迁移只在 SQLite :memory: 初始化应用；两个进程隔离检查通过，没有真实配置、.env 或外部连接。
- 本轮修改文件的 Ruff 静态、格式、Python 内存语法编译和 Git 差异空白检查通过（含未跟踪文件）。

历史成绩仅供追溯，不计入上述 45 个：F05B-1 为 15 项；F05B-1A 为 25 项；F05B-2 为 29 + 3 项；F05B-3 为 19 + 4 项。以下历史记录保留当时范围与边界，当前验收以本节为准。

## 本轮文件与复跑

仅修改 experiments/wagtail_f05b 下 3 个既有文件：

- test_http.py：新增一个真实 HTTP 异常回滚、重试和重复请求测试。
- run.py：新增 stage 模式，明确收集三个 F05B 测试模块，并执行迁移一致性检查；保留原模式。
- README.md：阶段最终验收与历史记录。

无新文件、模型或迁移，无批准视图、服务、角色、正式配置变更。

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py stage
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py compat
.\.venv\Scripts\ruff.exe check --no-cache experiments/wagtail_f05b/test_http.py experiments/wagtail_f05b/run.py
.\.venv\Scripts\ruff.exe format --check --no-cache experiments/wagtail_f05b/test_http.py experiments/wagtail_f05b/run.py
.\.venv\Scripts\python.exe -I -c "from pathlib import Path; [compile(p.read_bytes(), str(p), 'exec') for p in (Path('experiments/wagtail_f05b/test_http.py'), Path('experiments/wagtail_f05b/run.py'))]; print('Syntax OK: 2')"
git diff --check
```

## 最终状态与停止点

分支 fusion/wagtail-poc；HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变；暂存区为空。原有 AGENTS.md、三个角色/同步命令文件的修改及未跟踪 ADR-0002、experiments 成果保留。本轮只涉及上述 3 个文件。

未读取真实 .env、安装依赖、运行服务器、操作 Docker/持久库，未修改主 worktree，未暂存、提交、推送。结论为 **A：F05B 实验审核发布闭环通过**；完成后停止，不进入 F06。

---

# F05B-3 历史记录（以下为此前阶段）

2026-09-13：完成本轮任务，停止等待 F05B-4。未新增模型、迁移或第二套批准/发布逻辑。

## 入口与调用关系

通过 Wagtail 公开 register_snippet_listing_buttons hook 在知识内容列表显示“审核并批准”，仅对已有列表访问权限且通过现有资格校验的用户显示。点击进入任务审核页，再点击“批准并发布本次修订”。列表权限仅由合成夹具提供，未修改正式角色。

通过 register_admin_urls 注册：

- GET /cms/f05b/tasks/<任务ID>/review/：复用 check_approval_eligibility，通过后显示本任务的受审修订及 CSRF 表单。
- POST /cms/f05b/tasks/<任务ID>/approve/：仅调用 services.approve_review(任务ID, request.user)，成功返回中文确认页。

表单只提交 csrfmiddlewaretoken；任务来自 URL，审核人固定来自 request.user。额外 POST 字段、查询参数或上传文件返回 400。更换为另一个任务 ID 时按目标任务实际资格判断，不以 ID 变化本身认定越权。

沿用 require_admin_access 和每次会话恢复都会检查账号状态的 AccountStateBackend；批准使用 require_POST、csrf_protect。服务执行时重新校验，按钮可见性不是授权依据。预期拒绝仅捕获 ApprovalRejected：审核组/自审等 403，任务结束/关联异常等 409，正文为中文原因。GET 批准为 405，无效 CSRF 为 403，未登录或失效会话重定向登录。没有新增宽泛异常捕获。

## 修改文件

新增 5 个文件，均位于 experiments/wagtail_f05b：apps.py、wagtail_hooks.py、views.py、templates/wagtail_f05b/review.html、test_http.py。

修改 settings.py（仅 F05B 安装无模型实验 App）、run.py（增加 http 模式）、test_compat.py（验证原配置没有路由和按钮）、本 README。

approve_review、资格校验、TaskSubmission、共享 F05A 代码和正式模型/角色/配置均未修改，无新增迁移。

## 实际检查的旁路

沿用 F05A ReviewViewSet 和 URL 限制。枚举本内容类型已注册 Snippet urlpatterns，除 list、list_results、edit、inspect 外均指向 closed_operation。

真实 GET/POST 验证以下入口返回 403：原生 workflow_action approve、collect_workflow_action_data、取消审核、add/copy/delete/unpublish、revisions_revert、revisions_unschedule，以及本内容模型 bulk publish/unpublish/delete。

真实编辑 POST 验证 action-publish、action-submit、action-workflow-action、action-schedule、action-cancel-workflow、action-restart-workflow、overwrite_revision_id 均被拒绝。超级管理员同样不能走这些旁路。通用 publish 权限也不能绕过本批准入口的审核组、自审及修订关联检查。

原任务仍只暴露 reject。定时发布、下架、删除、复制、历史恢复和取消审核保持关闭。检查范围仅为本实验内容及此次注册的后台入口，不是整个 Wagtail 平台审计。

## 本轮实际测试

| 配置和范围 | 数量 | 结果 |
| --- | ---: | --- |
| F05B http：HTTP 11 项 + 服务回归 8 项 | 19 | 全部通过，3.855 秒 |
| F05A compat：原兼容 3 项 + 路由/按钮隔离 1 项 | 4 | 全部通过，1.134 秒 |

耗时不含内存迁移，subTest 不另计。没有重复 F05B-2 已通过的服务层异常注入，没有重跑全部历史套件。

实测覆盖：

- 列表真实渲染合法审核链接；任务页真实渲染 POST、具体任务 URL、CSRF 和批准按钮，自审用户不显示入口。
- 有效 CSRF POST 调用真实批准服务一次，actor 等于认证用户，正式 V1 切换受审 V2，发布日志仅增加一条；重复 POST 返回 409。
- GET 批准、缺失/错误 CSRF、未登录、停用/禁用/离职账号均不能写入。
- 打开表单后撤销审核组，保留后台准入，POST 仍因组资格拒绝。
- 创建者和本轮提交人，包括成为超级管理员后均拒绝；只有通用发布权限但不在审核组也拒绝。
- 伪造审核人、修订、任务等字段返回 400；跨对象修订绑定或缺失任务返回 409；任务驳回后过期 POST 返回 409。
- 对另一合法任务 ID 的请求按实际资格成功，只发布该任务内容，原任务仍进行中且原正式内容仍为 V1。
- 被拒请求前后检查任务、工作流、提交记录、修订、内容和日志快照；测试结束核对旧 Article/ArticleVersion/ReviewRecord 全字段、既有修订、内容主键和 Article 关联不变。
- 独立 F05A 配置不注册新路由（反向解析失败，实际 POST 为 404），列表无新按钮；原服务关闭及完成保护通过。

两个进程使用现有 .venv、合成配置、SQLite :memory:，隔离检查通过。Django check 无错误，各保留 108 条既有 SQLite 注释警告（0 silenced）。本轮无模型变化，未运行迁移一致性检查。相关 Ruff 静态/格式、Python 内存语法和差异空白检查在交付前执行。

## PowerShell 复跑

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py http
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py compat
.\.venv\Scripts\ruff.exe check --no-cache experiments/wagtail_f05b
.\.venv\Scripts\ruff.exe format --check --no-cache experiments/wagtail_f05b
git diff --check
```

使用 http 模式可排除既有服务故障注入；原默认 service 模式保留此前范围。未覆盖浏览器自动化、并发/PostgreSQL、完整平台审计、永久历史或任意 ORM/SQL 防篡改。

分支 fusion/wagtail-poc，HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变，暂存区为空，保留所有既有未提交成果。未读取真实 .env、安装依赖、运行服务器、操作 Docker/持久库，未修改主 worktree、暂存、提交或推送。

完成后停止，等待 F05B-4。

---

# F05B-2 历史记录（以下为此前阶段）

2026-09-13：完成实验服务，停止等待 F05B-3。仅新增程序服务，不新增后台按钮或 URL，不宣称完整 HTTP 入口保护完成。

## 入口、原生调用链与授权

入口：`experiments.wagtail_f05b.services.approve_review(task_state_id, actor)`。actor 必须来自服务端认证上下文；只接受任务 ID 和当前用户，不接受发布修订或先前资格结果。成功返回刷新后的 TaskState；失败抛出带 code 的 ApprovalRejected（PermissionDenied 子类）。

实际链路：

```text
approve_review（外层 atomic）
  → 重读 TaskState、WorkflowState
  → check_approval_eligibility（重读账号、组、自审身份及 TaskSubmission）
  → TaskState.approve(user=actor)
  → WorkflowState.update(user=actor)
  → WorkflowState.finish(user=actor)
  → F05B publish_reviewed 完成回调
  → _ReviewedPublishAction.execute()
  → Wagtail PublishRevisionAction._publish_revision()
```

定点核对 Wagtail 安装包：TaskState.approve 自行写批准人和完成时间，并推进 WorkflowState；finish 写工作流 approved 后立即调用 on_finish。默认回调发布 get_latest_revision，因此 F05B 通过自己的 WAGTAIL_FINISH_WORKFLOW_ACTION 替换它。服务只调用原生 approve，不再额外调用第二次发布；没有用 ORM 更新伪造批准状态。

F05B settings 继承 F05A 隔离配置，仅替换完成回调；F05A settings、共享 RejectOnlyTask、后台 ViewSet/URL 均未修改。RejectOnlyTask.on_action 和 get_actions 仍只支持驳回。本轮服务在业务校验后直接调用原生 TaskState.approve。

授权不是通用发布权限：服务在本次 WorkflowState 实例上附加一次性、非持久上下文，完成回调取用后删除。没有进程全局开关、永久权限跳过、角色权限增量或 user=None 发布。实验 PublishRevisionAction 子类使用任务审核授权代替通用 publish 权限检查：再次核对完成状态、批准人、账号、实际任务组、创建者/提交人排除、提交记录和修订；明确拒绝 skip_permission_checks=True。普通 Revision.publish 仍使用原生权限检查。此处是本次服务调用的授权适配，不声称防止任意 Python/ORM/SQL 调用内部实现。

## 受审修订与事务

- 唯一发布目标来自 TaskState.revision；TaskSubmission 必须唯一绑定该任务且 revision 一致，提交人仅从该记录读取。
- 校验要求任务是当前进行中的任务，修订属于同一内容且与当前允许批准的草稿一致。原生状态转换后，完成回调重新核对任务修订、提交记录及修订正文快照与进入服务时一致。
- 回调传给 PublishRevisionAction 的是任务指定的 Revision，绝不以最新草稿代替。仅支持当前单任务、即时发布实验；有计划发布时间时明确拒绝。
- 资格检查、原生任务/工作流转换、发布和结果校验全部位于 approve_review 的 atomic 内。异常会回滚任务、工作流、正式指针及日志；仅保证顺序请求，不保证并发安全。
- 成功后验证任务/工作流为 approved，KnowledgeContent.live=True 且 live_revision 等于受审修订。
- Article、旧版本指针、ArticleVersion、ReviewRecord 全字段不变；既有 Revision 全字段、KnowledgeContent 主键和 Article 关联保持不变。

## 本轮文件

新增 5 个文件（全部位于 experiments/wagtail_f05b）：

- services.py：批准服务、限定本次任务的发布授权适配。
- finish.py：可在 Wagtail 模型初始化时加载的回调，延迟导入服务避免循环导入。
- settings.py：F05B 专用完成回调配置。
- test_services.py：9 项服务专项。
- test_compat.py：原 F05A 配置下服务关闭测试。

修改 run.py 和本 README。未修改共享任务代码、正式模型、角色、配置或迁移；没有新增实验迁移。本轮未运行迁移一致性检查，既有迁移仅用于初始化 SQLite 内存测试库。

## 本轮实际测试

| 配置与范围 | 数量 | 结果 |
| --- | ---: | --- |
| F05B：服务 9 项 + 既有资格/提交身份 20 项 | 29 | 全部通过，最终 4.657 秒 |
| 独立 F05A：服务关闭 + 原提交/重提 + 原关闭动作/完成保护 | 3 | 全部通过，0.960 秒 |

耗时不含内存迁移，subTest 不另计，未重跑全部历史套件。两个进程均通过隔离检查，Django system check 无错误，各保留 108 条既有 SQLite 表/字段注释警告（0 silenced）。

服务证据：

- 无通用 publish 权限的合法第三方审核员批准 V2：TaskState/WorkflowState 为 approved，批准人和完成时间正确，正式 V1 切换 V2，发布日志仅新增一条。
- 从无正式版开始，批准前 read_live 为 None，批准后可正式读取。
- 驳回重提后使用新 TaskSubmission 判断身份、发布新任务 Revision，旧驳回任务及其提交记录保持不变。
- 创建者、当轮提交人、超级管理员自审或不在组、账号失效/禁用及撤销组资格拒绝；先前校验成功也不会绕过执行时的重新校验。
- 重复批准、已驳回任务、缺失任务/提交记录、错绑修订和出现新草稿均拒绝，快照不变，不产生额外发布。
- 批准 V2 后保存 V3 草稿，正式内容仍为 V2。
- 在原生任务及工作流已经 approved、发布底层操作尚未执行时注入异常；断言当时正式指针仍为 V1，异常后全部快照回滚，随后重试成功。
- 原生 TaskState.approve 不带本次服务上下文时拒绝并回滚；审核员直接 Revision.publish 仍因无通用权限拒绝。
- 每项服务测试结束重新核对旧业务记录、既有修订全字段及内容主键/Article 关联。既有资格测试继续验证只读 SQL 与快照。
- F05A 独立进程验证新服务返回 configuration_disabled，原提交/重提仍可用，原生后台动作及 finish 保护仍关闭。

相关 Python 文件 Ruff 静态、格式、内存语法编译以及 Git 差异空白检查通过（含未跟踪新文件）。没有读取真实 .env、安装依赖、启动服务器、操作 Docker 或持久数据库。

## PowerShell 复跑

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py compat
.\.venv\Scripts\ruff.exe check --no-cache experiments/wagtail_f05b
.\.venv\Scripts\ruff.exe format --check --no-cache experiments/wagtail_f05b
git diff --check
```

run.py 默认使用 F05B 合成配置执行 29 项；compat 使用独立 F05A 配置进程执行 3 项。保留此前 makemigrations 模式，本轮未调用。不要使用读取真实配置的 manage.py。

## 最终 Git 与停止点

分支 fusion/wagtail-poc，HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变；暂存区为空。所有既有未提交成果保留，本轮新增/修改仅限 F05B 目录。未修改主 worktree，未暂存、提交、推送。

停止等待 F05B-3；没有接入新 HTTP 批准入口，没有完成并发、永久历史或完整 HTTP 入口保护。

---

# F05B-1A 历史记录（以下为此前阶段，不代表当前执行范围）

此前完成 F05B-1A（2026-09-13）：补齐首次提交及驳回后重提的提交人绑定。只提供资格校验，未批准、未发布、未开放新按钮或 URL；停止等待 F05B-2。

## 根因与身份来源

F05A 重提调用原生 `WorkflowState.resume`，复用原 WorkflowState，新建 TaskState；`requested_by` 不更新，表示首次提交人。已定点核对安装包 `wagtail/models/workflows.py`：resume 日志虽然记录操作者，但关联旧 TaskState、旧 Revision，不能直接充当新任务的提交身份。本轮不通过“最近日志”、修订创建者或首次提交者推断。

采用最小实验模型 `fusion_f05a.TaskSubmission`，放在已安装的 F05A 实验 App 中，复用已有隔离配置：

| 字段 | 约束与含义 |
| --- | --- |
| task_state | OneToOne 主键，关联本轮实际 Wagtail TaskState，每个任务仅一条 |
| revision | 非空外键，记录该次提交的受审 Revision，与 TaskState.revision 交叉校验 |
| submitted_by | 非空外键，来自现有 HTTP 端点传入的服务端 request.user |

三项关联均使用 PROTECT。没有额外内容、审批状态或平行审核状态机，没有历史身份回填。

真实路径仍为已有 `POST /cms/f05a/<内容ID>/submit/` → `services.submit`。原生 start/resume 创建任务后，服务核对 TaskState.revision，再使用 `TaskSubmission.objects.create` 写入身份；全部位于已有同一个 atomic 事务内。重提生成新的 task_state 主键记录，不 update/upsert 旧记录。视图原有字段白名单拒绝 submitted_by、submitted_by_id、requested_by、user_id 等伪造字段。

## 资格入口

`check_approval_eligibility(*, content_id, task_state_id, user)` 返回不可变 `ApprovalEligibility(allowed, code, reason)`；调用方必须读取 allowed，不可把对象自身真值当作授权。

- 重读账号，要求已认证、已保存、is_active=True、account_status=active。
- 从当前实际任务读取审核组，要求真实成员关系；超级管理员不绕过。
- 任务、工作流须启用且进行中，并为当前任务；内容、工作流配置、Revision 的 ContentType/object_id、JSON 主键及 Article 关联须一致，受审修订为当前未发布修订。
- 创建者仍取 `TaskState.revision.user`；本轮提交人仅取 `TaskSubmission.submitted_by`。两者均不得批准，超级管理员同样受限。
- 缺少本轮记录或创建者时返回 identity_missing；记录与受审修订不一致时返回 identity_inconsistent。不再返回 submitter_unresolved，不依赖 requested_by 或原生日志回填身份。
- 其他原因码：allowed、account_invalid、reviewer_required、task_inactive、binding_invalid、revision_creator、review_submitter，均附中文原因。

校验只读，结果只表示当前读取时刻的资格，不是批准或可延后使用的授权令牌。没有新增并发控制，也未声称防止任意 ORM/SQL 篡改或完成永久历史机制。PROTECT 只保护关联目标，不等于记录不可被任意程序改写；受支持提交路径只新增记录。

## F05B-1A 修改范围

修改 7 个既有实验文件：

- `experiments/wagtail_f05a/models.py`：新增 TaskSubmission。
- `experiments/wagtail_f05a/services.py`：首次提交/重提同事务创建绑定。
- `experiments/wagtail_f05a/tests.py`：公共快照纳入提交绑定，供回滚和只读断言使用。
- `experiments/wagtail_f05b/eligibility.py`：改用本轮绑定记录。
- `experiments/wagtail_f05b/tests.py`：真实 HTTP 提交及身份、拒绝、回滚、重复提交验证。
- `experiments/wagtail_f05b/run.py`：隔离生成迁移模式、迁移一致性检查及定点 F05A 回归。
- 本 README。

新增 `experiments/wagtail_f05a/migrations/0002_tasksubmission.py`，通过现有虚拟环境在隔离配置下生成；已检查仅 CreateModel，含任务唯一主键及三个必要关联，无数据迁移或回填。没有修改正式模型、迁移、角色、同步命令或主 worktree。

## 本轮实际证据

25 项测试全部通过，执行耗时 3.913 秒（不含内存迁移），subTest 不另计：

- F05B 专项 20 项。
- F05A 定点 5 项：迁移和工作流绑定、提交/驳回/重提、重复提交与旧任务、跨对象/过期修订与伪造字段、提交/驳回中途异常回滚。
- 同一次运行 `makemigrations --check --dry-run`：No changes detected；既有及新增实验迁移在 SQLite :memory: 成功应用。
- Django system check 无错误；108 条既有 SQLite 不支持表/字段注释警告，0 silenced。
- 相关文件 Ruff 静态/格式检查、Python 内存语法编译、Git 差异空白检查通过（包括未跟踪实验文件）。

身份链证据通过重新查询数据库断言：

1. 首次真实 HTTP 提交后，旧任务记录 `(TaskState旧, Revision V2, 甲)`；身份是登录提交者，不是 V2 创建者。
2. 驳回后生成新修订，由乙真实 HTTP 重提；同一个 WorkflowState 的 requested_by 仍为甲，新记录为 `(TaskState新, Revision新, 乙)`，旧记录全字段不变。
3. 新修订由甲创建、乙提交：甲以 revision_creator 拒绝，乙以 review_submitter 拒绝，满足组资格的第三人允许；将甲乙改为超级管理员仍拒绝。
4. 缺记录拒绝，不回退到初次提交人；错绑修订拒绝；伪造身份字段返回 400，快照不变。
5. 首次提交和重提分别在“身份记录实际插入后”注入异常，确认任务和身份记录都已写入后抛错；事务结束后，两条新记录均不存在，内容/修订/工作流/任务/日志/身份全字段恢复至调用前快照。
6. 首次及重提的重复请求返回 409，不覆盖或新增记录；直接重复任务键触发数据库唯一约束。
7. 每次资格调用捕获 SQL 并要求全部为 SELECT，前后重新查询提交记录、任务、工作流、修订、日志、实验内容及 Article/ArticleVersion/ReviewRecord 全字段快照一致。

夹具仍借用 F05A/F04B 的旧正式 V1 与草稿构造；旧正式版夹具初始化不表示开放业务发布。本轮没有调用批准服务，没有运行未选中的历史测试。白名单子进程、-I、真实 .env/config/dotenv/网络/非内存数据库拦截保持生效。

## PowerShell 复跑

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05b/run.py
.\.venv\Scripts\ruff.exe check --no-cache experiments/wagtail_f05b experiments/wagtail_f05a/models.py experiments/wagtail_f05a/services.py experiments/wagtail_f05a/tests.py experiments/wagtail_f05a/migrations/0002_tasksubmission.py
.\.venv\Scripts\ruff.exe format --check --no-cache experiments/wagtail_f05b experiments/wagtail_f05a/models.py experiments/wagtail_f05a/services.py experiments/wagtail_f05a/tests.py experiments/wagtail_f05a/migrations/0002_tasksubmission.py
git diff --check
```

默认 run.py 已包含迁移一致性、内存迁移、Django check、20 + 5 项测试。仅需重新生成实验迁移时使用同一入口加 `makemigrations` 参数；不要改用导入真实配置的 manage.py。

## 基线、旧成果与停止点

分支 fusion/wagtail-poc；HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变；暂存区为空。原有 AGENTS.md、三个角色/同步命令改动、未跟踪 ADR-0002 和全部实验成果保留。Git 顶层仍显示这些既有项目；本轮修改的实验文件及新迁移都位于未跟踪 experiments 下。

F05B-1 历史：15 项通过，当时缺少可靠重提身份而保守返回 submitter_unresolved；本轮以上 25 项实际运行及新绑定机制取代该限制，历史成绩不计入本轮数量。

未读取真实 .env，未安装依赖，未操作 Docker、持久数据库，未暂存、提交、推送或修改主 worktree。新增迁移仅应用于内存测试库。完成后停止等待 F05B-2；未实现批准或发布。
