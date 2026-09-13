# F05A：最小审核提交与驳回验证

日期：2026-09-12。结论：**A：提交与驳回流程通过，可以规划 F05B。** 只完成提交和驳回，不开放批准/发布，不代表完整审核闭环。

## 基线和实际变更

- worktree：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`。
- 分支：`fusion/wagtail-poc`；完整 HEAD：`d59c87c660807d80e78727da3c25222c98e606dd`。
- 解释器：上述 worktree 的 `.venv\Scripts\python.exe`；实测 Python 3.13.13、Django 5.2.17、Wagtail 7.4.3。未安装或升级依赖。
- 修改 `experiments/wagtail_f04a/models.py`：加入 WorkflowMixin，继承顺序为 WorkflowMixin、DraftStateMixin、RevisionMixin；新增实验 submit_knowledgecontent 权限。没有第二套内容模型、审核表或业务状态机。
- 新增 `experiments/wagtail_f04a/migrations/0002_alter_knowledgecontent_options.py`：仅表达 Meta 权限变化。WorkflowMixin 的 GenericRelation 不新增数据库列；保留原 0001_initial，未重写历史。
- 修改 `experiments/wagtail_f04b/views.py`：从 F04B 原配置的路由集合移除因 WorkflowMixin 新出现的审核路由，维持原验收契约；F05A 用独立 ViewSet 注册这些原生审核路径的拒绝处理器。
- 本目录新增 15 个文件：__init__.py、apps.py、models.py、policy.py、services.py、views.py、settings.py、urls.py、wagtail_hooks.py、run.py、tests.py、migrations/__init__.py、migrations/0001_initial.py、templates/wagtail_f05a/review.html、本 README。
- 任务开始已有 44 个成果文件，除上述两份必要修改外其余 42 份 SHA-256 不变。F01 文档、三个角色/管理命令文件、正式配置/模型/迁移和主 worktree 均未修改。

## 原生工作流与实验适配

已定点核对安装包 workflows.py 的 WorkflowMixin、Workflow.start、WorkflowState.resume/finish、Task.start/on_action、TaskState.reject，以及 Snippet 工作流 URL 和 action 扩展。

夹具创建一个 Workflow、一个 RejectOnlyTask、一个 WorkflowTask 排序关系和临时审核组，通过原生 WorkflowContentType 关联 KnowledgeContent 的 ContentType。非 Page 模型的原生关联是模型级共享工作流，不是每篇内容单独一条配置。

RejectOnlyTask 继承 Wagtail AbstractGroupApprovalTask，具有原生 Task 父记录和 groups 关系；F05A 初始迁移只创建这个任务类型及其组关联，没有平行审核记录。实际审核仍写 Wagtail WorkflowState/TaskState：

- WorkflowState 保存对象 ContentType/object_id、工作流、初次提交者及当前任务；
- TaskState.revision 是指向实际 Revision 的外键，保存任务状态、驳回人、时间和说明；
- 初次提交调用 Workflow.start；其原生 Task.start 读取最新修订。因此实验服务先验证请求修订就是当前未发布草稿，启动后再验证 TaskState.revision 与指定 ID 相等，任一不符整体回滚；
- 驳回调用任务的 reject action → 原生 TaskState.reject，工作流变为 needs_changes；
- 保存新草稿后调用原生 WorkflowState.resume：保留同一逻辑 WorkflowState，新增绑定新修订的 TaskState；旧 rejected TaskState 不改写。不是另建一份平行审核状态。WorkflowState.requested_by 保留初次提交者，重提动作的操作者由原生日志记录。

实验 services.py 包装业务前置校验和 atomic；独立后台端点处理认证、对象定位、CSRF、字段白名单与 400/409 响应。没有在 Signal 内编写核心业务状态变更，没有修改上游源码或用运行时 monkey patch 实现功能；测试 mock 只用于故障注入。

## 开放操作和权限

入口：

- GET `/cms/f05a/<内容ID>/review/`：实验操作页，显示修订 ID/工作流状态，提供提交当前修订或带说明驳回表单；不是完整审核预览界面。
- POST `/cms/f05a/<内容ID>/submit/`：仅接收 revision_id、CSRF。
- POST `/cms/f05a/<内容ID>/reject/`：仅接收 task_state_id、comment、CSRF。
- 原 Snippet 编辑路径继续处理标题/摘要/正文草稿。

| 操作 | 必须满足的服务端条件 |
| --- | --- |
| 编辑草稿 | 原 access_admin + change_knowledgecontent，账号有效，当前无 in_progress 审核 |
| 提交/重提 | access_admin + change_knowledgecontent + submit_knowledgecontent，账号有效；当前未发布草稿、归属正确；没有进行中的审核；重提必须是新修订 |
| 驳回 | access_admin、账号有效、属于当前 RejectOnlyTask 的临时审核组；任务属于 URL 对象、正是当前进行中的任务 |
| 批准、发布、取消审核等 | 本轮实验后台始终拒绝，包括 superuser |

账号有效表示已认证、已保存、is_active=True、account_status=active。复用 F03A 认证后端，在每次会话恢复时重新查询状态。系统角色不改动，临时组只存在内存夹具。超级管理员并不自动成为本任务审核组成员；提交仍沿用 Django 权限语义，驳回明确要求组成员。

提交人取 request.user，不能从 POST 指定；未知内部字段返回 400。错误/过期/跨对象修订或任务返回 409；无权限由 Wagtail 返回拒绝或重定向 /cms/，非正常账号已有会话重定向登录。重复提交、重复驳回、重提旧草稿及旧任务重放均不产生新写入，不出现确定性 500。

## 编辑锁、驳回和重提实测

真实请求完成：正式 V1 → 后台保存草稿 V2 → POST 提交 V2 → 审核员真实 POST 驳回 → 编辑真实 POST 保存 V3 → POST 重提 V3。

- 提交后 current_task_state.revision_id 正确指向 V2，正式 read_live 始终返回 V1。
- ReviewEditView 在 POST 和实际 save_instance 边界重新查询 in_progress 状态，审核期间拒绝保存。覆盖先 GET 打开旧表单、随后提交审核、再 POST 旧表单；普通编辑者和 superuser 均返回 409，内容和修订不变。
- 驳回后任务记录为 rejected，带审核员、完成时间、说明；WorkflowState 为 needs_changes。
- 新草稿 V3 可保存并重提，当前任务换为新 ID 且关联 V3，旧 V2 修订及 rejected 任务逐字段不变；再次对旧任务发请求被拒绝。
- 每个专项测试结束重新查询 Article 全字段、两个非空旧版本指针、两条 ArticleVersion、一条 ReviewRecord，与初始夹具快照完全一致；正式 V1 及历史修订保持不变。

这是顺序请求验证。未实现数据库级并发锁，也未宣称状态检查与写入之间的并发竞争已经解决。

## 关闭操作和完成保护

F05A ViewSet 复用 F04B 的草稿 action 白名单、字段白名单、选择器拒绝和既有关闭路由；显式拒绝 WorkflowMixin 新增的 workflow_action、collect_workflow_action_data、confirm_workflow_cancellation、workflow_history、workflow_history_detail 路由。没有 PreviewableMixin，故无 workflow_preview 入口。

超级管理员真实 GET/POST 覆盖原生 approve/reject 动作路由、动作参数收集、取消确认、工作流历史；原生 reject 路由同样关闭，只允许上述经过绑定校验的实验 reject 端点。还验证 add/copy/delete/unpublish、历史恢复、unschedule、通用批量 delete 路由，以及 action-publish、action-submit、action-cancel-workflow、action-restart-workflow、action-workflow-action、action-schedule、overwrite_revision_id 均不能改变数据。

实验 URL 同时封闭 /cms/workflows/ 下的工作流和任务管理、/cms/groups/、/cms/users/，以及 /admin/auth/group/，避免开放审核组后台管理。未给普通夹具任何上述管理权限。

RejectOnlyTask.get_actions 只提供 reject，on_action 显式拒绝其他动作，不依赖按钮隐藏。F05A 配置通过公开 WAGTAIL_FINISH_WORKFLOW_ACTION 指定 forbid_finish，抛出 PermissionDenied，替代原生“完成后发布最新修订”。实际调用任务 approve 与 WorkflowState.finish 均被拒绝，finish 已写入的批准状态随事务回滚，正式版不变。这个保护仅属于 F05A 配置；F04A 程序发布仍作为历史机制测试保留，不等于本轮开放发布。

## 事务和失败证据

提交和驳回服务都使用外层 atomic，覆盖前置校验后的原生多步写入。实际 HTTP 请求分别注入：

1. 提交创建工作流/任务记录后，原生日志步骤抛错：内容、Revision、WorkflowState、TaskState、Wagtail 日志全部回滚；
2. 驳回已写 TaskState 后，状态日志步骤抛错：任务、工作流和相关日志完整回滚。

与故障前重新查询快照完全一致。故障注入预期抛 RuntimeError；正常重复或非法操作不是这些故障测试，不返回确定性 500。atomic 不等于并发安全，也未实现业务审计或 Outbox。

## 本轮检查与历史成绩区分

| 本轮实际执行配置 | 数量 | 结果 |
| --- | ---: | --- |
| F05A（启用单步骤工作流） | 11 项 | 全部通过，最终 3.682 秒 |
| F04A 原配置 | 17 项 | 全部通过，1.179 秒 |
| F04B 原配置 | 28 项，其中 11 后台 + 17 模型回归 | 全部通过，5.330 秒 |

上表为本轮真实执行，耗时不含迁移，subTest 不另计；F04B 内含重复的 F04A 回归，不当作 56 个独立场景。历史 F04B 28 项只是此前报告成绩，不用于替代本轮执行。

三个进程均从空 SQLite 内存库应用已有和相应新增迁移，模型/迁移一致性输出 No changes detected。各自运行 Django system check，0 错误、108 条既有 SQLite 注释警告、0 silenced：97 条 fields.W163（字段注释），11 条 models.W046（表注释）。警告保留，不作为 PostgreSQL 通过或失败证据。

首次专项有一处权限拒绝断言预期 403，而 Wagtail 实际重定向 /cms/；修正为核对拒绝目标和全部数据不变后通过。生成迁移继承的长 help_text 进行了等值分行格式修正。无遗留失败。

相关 Python Ruff 静态/格式、语法及 Git 空白检查通过；没有执行无关历史完整套件。白名单子进程 -I、独立 settings、.env/config/dotenv/网络/非内存 SQLite 拦截、迁移前内存库断言继续生效；migrate(run_syncdb=False)，未关闭迁移或屏蔽检查。邮件使用 locmem，任务使用 DummyBackend，无外部通知。

## PowerShell 复跑

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f05a/run.py
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f04a/run.py
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f04b/run.py
.\.venv\Scripts\ruff.exe check experiments/wagtail_f05a experiments/wagtail_f04a/models.py experiments/wagtail_f04a/migrations/0002_alter_knowledgecontent_options.py experiments/wagtail_f04b/views.py
.\.venv\Scripts\ruff.exe format --check experiments/wagtail_f05a experiments/wagtail_f04a/models.py experiments/wagtail_f04a/migrations/0002_alter_knowledgecontent_options.py experiments/wagtail_f04b/views.py
git diff --check
```

三个入口均包含迁移一致性、隔离检查、内存迁移、system check 及对应测试。已有迁移无需重新生成；不要改用读取真实配置链的 manage.py。日志 validation.log、wagtail_f04a-regression.log、wagtail_f04b-regression.log 与工具缓存沿用既有忽略规则。

## 最终状态和未验证事项

HEAD/分支未改变；暂存区为空。保留全部已知未提交成果，本轮只增加上述实验文件/迁移及两份共享实验修改。没有提交、推送、修改 Git 配置、清理、主 worktree 写入、Docker 或持久数据库操作；没有启动真实服务器。

未验证批准后发布、自审身份限制、员工受众、正式角色审核权限、PostgreSQL、并发、永久历史保留或浏览器交互。审核员若同时是作者，本轮没有实现作者排除，不能宣称自审防护完成。Task/Revision/Workflow 直接 ORM/SQL 和任意程序绕过也不属于已封闭边界。

本轮只验证提交与驳回，不宣称完整审核流程完成。完成后停止，未进入 F05B，未开放批准或发布。
