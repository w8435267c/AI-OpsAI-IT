# F04B：最小 Snippet 后台草稿编辑与入口保护

日期：2026-09-12。结论：**A：最小后台草稿编辑通过，可以规划下一阶段。** 本任务不执行 F05，不开放发布或审核。

## 实际基线和修改范围

- 目录：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`。
- 分支：`fusion/wagtail-poc`；完整 HEAD：`d59c87c660807d80e78727da3c25222c98e606dd`。
- 解释器：上述目录 `.venv\Scripts\python.exe`；本轮核对 Python 3.13.13、Django 5.2.17、Wagtail 7.4.3，未安装或升级依赖。
- 仅新增本目录 9 个交付文件：`__init__.py`、`apps.py`、`settings.py`、`urls.py`、`views.py`、`wagtail_hooks.py`、`tests.py`、`run.py`、`README.md`。
- F04A 未修改，继续复用 fusion_f04a.KnowledgeContent 和 0001_initial 迁移。没有第二组内容表、没有新迁移。F01～F04A 及角色/命令等 35 个既有文件前后 SHA-256 一致。
- 独立设置继承 F04A → F03B → F03A → F02 隔离配置；账号认证后端仍为 F03A AccountStateBackend。未修改正式配置、业务模型、员工 Selector 或 SYSTEM_ROLES。

## 注册、权限与开放操作

通过公开 `register_snippet(KnowledgeContentViewSet)` 注册非 Page 模型；采用 SnippetViewSet 的 panels、edit_view_class、index_view_class、chooser_viewset_class、get_urlpatterns 扩展及 construct_snippet_action_menu hook，没有修改上游或运行时猴子补丁。测试中使用的 mock 仅用于故障注入及委托真实方法的调用观察。

编辑表单仅 title、summary、body 三字段。模型级权限通过自定义 ModelPermissionPolicy 限定为 view/change；其他 action 即使 superuser 也不允许。编辑页继续使用 Wagtail 原生表单和草稿机制，不复制 F04A 身份保护逻辑。

| 合成账号权限 | /cms/ | Snippet 列表 | 只读 inspect | 编辑/保存草稿 |
| --- | --- | --- | --- | --- |
| 无 access_admin，仅 change | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| 仅 access_admin | 可进入 | 拒绝 | 拒绝 | 拒绝 |
| access_admin + view_knowledgecontent | 可进入 | 可查看 | 可查看 | 拒绝 |
| access_admin + change_knowledgecontent | 可进入 | 可查看 | 仍按独立 view 权限判断 | 允许 |
| 正常 superuser | 可进入 | 可查看 | 可查看 | 仅允许草稿编辑，关闭操作仍拒绝 |

view/change 均属 `fusion_f04a`。临时组名为 `F04B fixture ...`，普通编辑夹具只含 access_admin 和 change_knowledgecontent、无直接权限且非 staff；这是最小实验授权，不是正式角色内容权限设计。V1 仅由 F04A 合成发布夹具在内存中预先发布。

## 实际路由与服务端关闭边界

该模型的基础路径为 `/cms/snippets/fusion_f04a/knowledgecontent/`。保留原 URL 名称以兼容模板反向解析，关闭的处理器统一返回 403。

| 实际注册路径（相对基础路径） | 本轮处理 |
| --- | --- |
| 空路径、results/ | GET 列表；POST 405 |
| edit/<pk>/ | 有 change 权限可 GET、POST 追加草稿 |
| inspect/<pk>/ | 有 view 权限可 GET 查看数据库内容；POST 405 |
| add/、copy/<pk>/、delete/<pk>/ | GET/POST 403 |
| usage/<pk>/、history/<pk>/、history-results/<pk>/ | GET/POST 403，不提供历史恢复界面 |
| history/<pk>/revisions/<revision_id>/revert/ | GET/POST 403 |
| history/<pk>/revisions/compare/<revision_id_a>...<revision_id_b>/ | GET/POST 403 |
| history/<pk>/revisions/<revision_id>/unschedule/、unpublish/<pk>/ | GET/POST 403 |

测试比较完整 viewset URL 名称集合，避免漏掉实际注册入口。模型没有 Previewable/Workflow/Lockable Mixins，不注册对应预览、审核、锁定路由。

另完整关闭自动注册的选择器：`/cms/snippets/choose/fusion_f04a/knowledgecontent/` 下 choose、results、chosen/<pk>、chosen-multiple、create 五类 GET/POST 均 403。Wagtail 通用批量入口独立于 SnippetViewSet，所以实验 urls.py 在 /cms/ include 之前拦截 `/cms/bulk/fusion_f04a/knowledgecontent/<action>/`；实际测试 delete、publish、unpublish GET/POST，含 id 参数，全部 403。

编辑视图 get_available_actions 只返回 edit。GET/POST 中所有非 save/edit 的 action-*、以及 overwrite_revision_id、revision_id、action 参数明确返回 403；测试覆盖 publish、submit、delete、unpublish、copy、revert、schedule、未知 action 和修订覆盖参数。菜单只保留保存，列表取消批量选择框；安全性由服务端权限/路由/action 拦截承担，非菜单隐藏。

## 草稿、身份和事务证据

- 实际“保存草稿”按钮为普通 submit，无 name 属性；合法请求提交三字段及有效 CSRF，Wagtail 默认 action 为 edit。重新 GET 可见真实表单字段和按钮。
- 真实 POST 经 Wagtail CreateEditViewOptionalFeaturesMixin.save_instance 调用现有 KnowledgeContent.save_revision；委托真实方法的 spy 确认调用一次。Wagtail 对 live 对象采用 form.save(commit=False)，追加修订，不写正式正文。
- 发布夹具 V1 → 后台 V2 草稿后，live_revision、正式数据库正文及 read_live 仍为 V1；再次打开编辑页显示 V2 的标题、摘要、正文。再次保存 V3 又追加修订，V1/V2 原修订逐行不变。
- article/article_id、pk/id、live、live_revision/latest_revision 及其 _id、go_live_at、expire_at 等非表单字段按明确三字段白名单忽略；伪造这些值不会改绑、覆盖其他对象、发布或计划发布。修订 action/overwrite 参数则明确拒绝。
- 对象以服务器 URL 定位，沿用模型级 change 权限；编辑另一个合法 URL 目标是已授权操作，测试确认 POST 中伪造 pk 不会重定向写入第一个对象。未新增组织级对象权限。
- 所有场景结束均重新查询 Article 全字段、非空旧正式/工作版本指针、两条旧 ArticleVersion、一条旧 ReviewRecord；与初始快照一致。旧 Wagtail 修订同样核对未改写。
- DraftEditView.post 外层 atomic 包住真实后台表单、追加修订、日志及后置 hook；原 Wagtail 保存块自身也有事务。本轮在追加修订后的 Wagtail 日志调用注入 RuntimeError，真实 HTTP POST 整次回滚，内容/修订/日志快照和正式 V1 均不变。未实现未来业务审计/Outbox，也不宣称任意框架调用均具备该事务边界。

关闭自动保存 WAGTAIL_AUTOSAVE_INTERVAL=0，避免上游自动保存使用 overwrite_revision_id 与本轮追加契约冲突。本轮提供手动保存；手工伪造覆盖参数同样被拒绝，不修改 F04A。

## 本轮实际验证

| 本轮执行 | 数量 | 最终结果 |
| --- | ---: | --- |
| F04B 专项真实请求 | 11 个 test 方法 | 全部通过 |
| F04A 回归（同一进程已注册 Snippet） | 17 个 test 方法 | 全部通过 |
| 合计，subTest 组合不另计 | 28 | 全部通过，最终测试耗时 3.483 秒，不含迁移 |

专项覆盖匿名/无入口、仅入口、只读与修改分离、合法保存和再次编辑、已有会话 inactive/disabled/departed 的 GET/POST、无效/缺失 CSRF、身份状态伪造、URL 定位、普通编辑者与超级管理员的关闭操作、以及真实保存中途异常回滚。所有客户端启用 CSRF，合法保存与关闭操作 POST 使用有效令牌，避免把缺 CSRF 当作权限防护。

历史成绩单列：F03B 报告 89 项、F04A 原报告 17 项是此前记录；本轮新运行结果为上述 28 项，未重跑 F01～F03B 或无关完整套件。没有改共享代码，F04A 17 项特意在 Snippet 已注册配置中回归，以检验注册副作用。

首次执行 28 项中 1 项因测试误以为保存按钮具有 name="action-save" 而失败；核对实际 HTML 后使用真实普通提交行为，修正测试再执行，28 项通过。未放宽草稿隔离、权限或回滚断言，无遗留失败。

- 内存库从空开始应用所有已有及 F04A 实验迁移，迁移图/外键回归通过；makemigrations --check --dry-run 输出 No changes detected。
- Django system check（测试运行器含数据库检查）：0 错误、108 条既有警告、0 silenced。97 条 fields.W163 为 SQLite 不支持字段注释，11 条 models.W046 为不支持表注释；保留显示，不作为 PostgreSQL 验证证据。
- 本轮新增 8 份 Python 的 Ruff 静态、格式及语法检查通过；Git diff --check、新增文件逐份空白及范围审查通过。
- 启动器保持 -I、白名单环境、独立 settings，拒绝真实 config/dotenv 导入、.env 读取、网络连接/DNS、非内存 SQLite；迁移前断言默认/测试库均为 :memory:，run_syncdb=False，不关闭迁移。无违规访问。

## 完整 PowerShell 复跑命令

以下入口包含 F04B 专项、注册状态下 F04A 回归、迁移一致性和系统检查，不使用正式 manage.py 配置链：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f04b/run.py
.\.venv\Scripts\ruff.exe check experiments/wagtail_f04b
.\.venv\Scripts\ruff.exe format --check experiments/wagtail_f04b
.\.venv\Scripts\python.exe -I -c "import ast,pathlib; files=list(pathlib.Path('experiments/wagtail_f04b').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8-sig')) for p in files]; print('Syntax OK',len(files))"
git diff --check
```

日志 validation.log、Python/Ruff 缓存沿用既有忽略规则，不进入 Git，不修改 .gitignore。未启动 HTTP 服务；真实请求指 Django 测试 Client 请求处理链，未做浏览器 JavaScript 或视觉验收。

## 最终状态及已知限制

工作区保留 F01～F04A 未提交成果，新增 F04B 九文件；暂存区为空。未操作主 worktree、真实 .env、持久数据库、Docker；未安装依赖、暂存、提交、推送或修改 Git 配置。

尚未实现审核、发布 UI、员工受众、正式角色内容权限、PostgreSQL、并发和永久历史保留；没有后台新增、编号服务或内容复制能力。F04A 程序发布仅用于合成夹具，不是业务发布入口。

保护结论仅覆盖本轮注册视图、action、选择器和追踪的通用批量 URL，不代表整个 Wagtail 平台完成安全审计。直接 ORM/SQL、程序发布、清理命令、其他未来注册途径及生产部署仍需独立设计验证。后台编辑权限不等于员工受众阅读权限。
