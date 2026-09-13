# F06A：员工读取与受众规则适配设计

日期：2026-09-13。状态：设计完成，F06B 待另行授权；本轮只新增本文件，不实现选择器、API、页面或迁移。

结论：保留原员工选择器的旧发布契约，提取同一套账号、文章可用状态和受众过滤逻辑；新增明确的实验详情读取路径，独立核验 Wagtail 正式修订及其批准证据。不伪造 ArticleVersion、不补旧发布指针、不隐式混读。

基线：fusion/wagtail-poc，HEAD d59c87c660807d80e78727da3c25222c98e606dd，暂存区为空。F05B 的 45 个不重复测试通过仅为此前报告，本轮未重跑，也不作为本轮实测成绩。

## 1. 当前实现 → 实验方案 → 下一步测试

| 规则 | 当前实际实现 | 融合实验方案 | F06B 必要测试 |
| --- | --- | --- | --- |
| 账号 | selectors._user_account_allowed 要求 accounts.User、is_authenticated、非空 pk、非 _state.adding、is_active=True、account_status=active；disabled/departed 拒绝。它检查传入用户字段，不主动重读账号 | 保留旧函数语义；新详情入口先拒绝匿名/未保存，再按主键重读当前 User 后调用共享过滤，避免过期账号对象继续读取 | None、匿名、未保存（含赋已存在 pk）、停用/禁用/离职、已删除账号；持旧对象但库内已禁用时新路径拒绝 |
| 文章/空间/生效时间 | Article.article_status=active、space.is_active=True；Article.effective_at 为空或 <= now。Category.is_active 和 Article.review_due_at 当前不参与过滤 | 全部沿用；统一一次服务端 now 用于文章及部门时间判断，不把分类停用/复审到期新增成阅读限制 | 空/过去/恰好 now/未来生效；空间停用；分类停用与复审日期不擅自改变旧契约 |
| all_employees | 文章 audience_policy=all_employees 即允许通过账号门槛者，再排除 deny；不要求显式全员 allow | 原样复用文章策略，不从空间 default_audience_policy 动态继承 | 无规则可读；匹配 deny 后不可读；改空间默认值不改变文章现有策略 |
| it_only | 仅当属于 KNOWLEDGE_IT_USER_GROUP_ID 绑定的启用 accounts.UserGroup；配置经 parse_it_group_id 校验，缺失/非法/不存在/停用/非成员均不允许。不是 is_staff 或名为 IT 的部门/系统角色 | 复用原配置解析及 _is_it_staff，不增加别名推断 | 配置缺失/非法/边界、组停用、成员撤销；仍受 deny 限制 |
| restricted | ArticleAudience 中 department/user_group/user 任一有效 allow 即可；无匹配拒绝；未知策略拒绝；不一致的 all_employees/it_only allow 不扩大范围 | 复用 _restricted_allow_exists 和文章策略组合 | 三类 allow、无规则、仅 deny、未知策略及不一致 allow |
| 直接用户 | ArticleAudience.user_id 与当前 user.pk 精确匹配，allow/deny 都按 audience_type=user 和 effect 匹配 | 原样复用，不将作者/负责人自动当作用户 allow | 指定用户匹配/不匹配及同用户 allow+deny |
| 部门/成员期限 | UserDepartment + Department.is_active；effective_at 为空或 <= now，expired_at 为空或 > now；多部门并集、无父子继承，is_primary 不特殊 | 原样复用 _active_department_ids；同一有效成员集合用于 allow 和 deny | 生效边界含等于、失效边界不含等于、多部门、主部门不特殊、父子不继承；停用/过期部门 deny 也不匹配 |
| 内容用户组 | UserGroupMembership(user,user_group) + UserGroup.is_active；成员只有 created_at，没有 effective_at/expired_at 或独立 is_active | 不补造有效期；当前成员关系存在且组启用才参与 allow/deny；Django Group 仍是系统操作角色 | 成员新增/撤销、组停用；组停用后 allow 与 deny 均不匹配 |
| deny 与后台身份 | _deny_exists 对三种策略统一覆盖 allow；只匹配有效 department/user_group/user deny。staff、superuser、编辑员、审核员、知识管理员、作者、空间负责人无阅读绕过 | 同一公共过滤；F05B 审核组权限不是员工阅读权 | 跨类型 allow/deny 冲突；后台角色/作者/审核员有管理权但无受众时不可读 |
| 只读正式内容 | 旧路径要求当前旧版本为 published；F04A read_live 仅从 live_revision 重建 title/summary/body，不读最新草稿，但缺员工受众和批准证据检查 | 新路径要求 live=True、live_revision 有效且归属正确、存在同修订有效批准证据；新草稿/审核中/驳回不替换旧正式版 | 首版批准前不可读，批准后可读；V1 正式且 V2 草稿/在审/驳回仍读 V1；V2 批准后切换；V3 草稿不泄露 |
| 下架/归档 | ArticleStatus 为 active/offline/archived，旧选择器只准 active | 即使 KnowledgeContent.live=True，Article 为 offline/archived 也拒绝；文章与空间状态实时读取 | 下架/归档/空间停用后的下一次调用立即拒绝，不修改 live 字段来凑结果 |
| 新旧发布指针 | visible_articles 同时依赖 current_published_version 非空、status=published、article_id=本 Article.pk | 旧入口完整保留这三条；新入口使用 Wagtail 正式证据，不要求旧指针，不回填旧表 | 旧路径继续拒绝空/非 published/跨文章指针；新路径在旧指针为空时可读取经 F05B 批准的新正式内容；旧表及指针全字段不变 |

上述语义以本地代码为准。ArticleAudience 本身没有成员有效期字段；用户组的 created_at 不是期限字段。旧选择器返回 Article QuerySet/布尔值，不是已经实现的员工 HTTP 详情页。

## 2. 旧发布指针耦合位置与最小提取

直接证据：`apps/knowledge/selectors.py` 的 visible_articles（224～262 行）。240～248 行同时过滤文章/空间/日期与旧发布条件，其中 243～245 行为：

- current_published_version__isnull=False；
- current_published_version__status=VersionStatus.PUBLISHED；
- current_published_version__article_id=F("pk")。

can_read_article（265～273 行）调用 visible_articles(...).exists()，因此同样依赖旧指针。Article.clean 在 models.py 432～437 行另外校验旧指针归属及 published 状态，但不能替代读取查询的限制。

F06B 最小方案（本轮不修改）：

1. 在同一个 apps/knowledge/selectors.py 提取内部 `_audience_eligible_articles(user, *, base=None, now=None)`（候选名）：承接当前 visible_articles 的账号门槛、唯一 base 规范化、文章 active、空间启用、生效时间、文章策略 allow 和 deny；只移出上面三条旧发布条件。该内部函数返回受众及可用状态候选集，不保证已发布，不可直接返回给员工。
2. 原 visible_articles 保持公开签名，调用公共过滤后始终叠加三条旧发布条件；can_read_article 的调用关系保持不变。不添加 require_published=False 一类开关，不改变正式路径行为。
3. 新实验详情函数复用同一个公共过滤，得到允许的 Article 后独立核对 Wagtail 正式存在性。受众表达式只在 selectors.py 维护一份；实验文件不复制 allow/deny/IT/成员期限算法，也不向正式模块引入 Wagtail 依赖。
4. 保留 _unique_article_base 全部契约：原 base 范围、数据库别名、合法排序及去重、select_related/prefetch、延迟求值、非法 base 的异常，以及原 visible_articles/单篇判断一致性。保持先规范化 base、再检查账号的调用顺序；不借本轮提取更改旧账号对象检查行为或查询规模。

该提取不等于放开旧发布限制。两个公开读取路径分别负责自己的发布判断，调用方没有通过 HTTP 参数关闭受众、发布或改变 now 的入口。服务端测试时钟也不得成为未来客户端权限参数。

## 3. 新实验详情读取契约

候选入口：`read_employee_article(article_id, user)`，放在 experiments/wagtail_f06/readers.py；article_id 指稳定 Article 身份，仅为内部 Python 参数，本阶段无 URL/API 设计。

顺序如下：

1. 验证认证用户为已保存账号，重读账号当前状态；使用一次服务端时间，通过公共过滤在指定 Article 范围内查询。
2. 不通过时统一返回 None；先完成此步再载入正文，不向无权限者返回标题、摘要、存在性差异或内部拒绝原因。
3. 以 Article 主键找唯一 KnowledgeContent（现有 OneToOneField，反向名 f04a_content）。要求 live=True、live_revision_id 非空。
4. 复用 F04A checked_revision(content, live_revision_id)：核对 Revision.content_type、base_content_type、object_id，以及 JSON 中 pk 与 article 对应当前 KnowledgeContent/Article。缺失或不一致统一不可读。
5. 按 ADR-0002 第 3 节要求，核对该 live_revision 的已批准证据，而非只信 live：匹配 TaskState.revision、status=approved、finished_by/finished_at 非空，其 WorkflowState.status=approved、内容类型/对象身份一致，完成工作流的 current_task_state 指向该任务；TaskSubmission.task_state 与 revision 同时匹配且提交人存在。要求有效证据无歧义，缺失/错绑/相互矛盾拒绝。历史创建者及提交人身份应存在，finished_by 不得等于受审修订创建者或本轮提交人。
6. 这是已发布证据核验，不再次运行 check_approval_eligibility：该函数要求 in_progress 及 latest_revision，不能用于读取旧正式版。也不因历史审核员后来离组/禁用而撤销所有已发布内容；当前员工仍按当前账号和受众重新判断。新的正在进行工作流不应遮蔽旧已完成工作流的正式证据。
7. 从已核对的 live Revision.content 经 KnowledgeContent.with_content_json 重建快照，只返回 title、summary、body（候选只读结果）。三个字段全部取同一正式修订；不返回 Article.title，不返回可随草稿变化的 KnowledgeContent 实例字段，不调用 get_latest_revision/as latest draft。当前实验 body 是 TextField，旧 ArticleVersion.body 为 JSONField，不能假装两者已完成格式迁移。

无匹配内容、无正式版、权限不足和可识别的关联异常均返回同一种 None，不隐式回退。只捕获可预期的缺失、输入格式或关联校验异常，不用宽泛异常掩盖程序错误。结果不是 ORM 实例，避免调用方顺手读取草稿字段。

当前 F04A read_live 没有 user 参数，也不检查 Article 状态、受众或同修订批准证据，因此继续仅作为实验机制辅助；不能直接包装成员工接口就视为完成授权。

## 4. 新旧边界、日期与具体待决点

- 本阶段不需要旧内容回退：新路径只读 F05B 审核发布的 Wagtail 内容；只有旧 ArticleVersion 的文章在新路径中不可读，但旧路径照常工作。一个 Article 两侧都有内容时也明确由调用的路径决定，禁止 new-or-old 隐式混读。
- 生效日期仍取实际存在的 Article.effective_at；review_due_at 仍为 Article 字段且当前不自动使文章失效。不得将草稿 go_live_at 当成员工读取生效时间。F05B 当前拒绝非空 go_live_at，仅支持即时发布。
- ADR-0002 将 go_live_at/复审日期迁移到受审内容写成候选正式切换目标，同时明确当前最小验证阶段保留旧模型；这不是已实施的日期归属。F06B 不迁移日期、不同步投影、不重新设计失效模型。正式日期迁移与切换冲突仍须另行确认。
- 正式批准证据永久保留尚未建立；现有 TaskState + WorkflowState + TaskSubmission 可用于最小实验读取校验，但不能证明任意 ORM/SQL 篡改被阻止。F06B 缺证据时拒绝，不新增永久历史表或修复历史数据。
- F04A/F04B 的旧 V1 夹具由 publish_for_test 直接发布，可能没有 F05B 批准证据。F06B 员工可读 V1 的新夹具必须真实调用 F05B 提交/批准服务生成证据，不能补造审核状态或复用直发夹具假称已审核。直发无证据内容应有明确拒绝用例。
- 测试运行方式有具体边界：test_selectors.py 是 Django TestCase；test_selector_boundaries.py 是 pytest 函数，其中 test_real_base_settings_parser 会 runpy 正式 base 并 mock dotenv，违反现有 F05B 隔离导入防护。不得把后者整个模块直接加入 DiscoverRunner 并声称测试执行过；F06B 应在隔离专项中覆盖其直接相关 base/账号/IT 配置断言，或后续单独设计明确的隔离 pytest 运行方式，不放松 .env/config 防护。本方案优先前者，仅迁移必要断言，不复制受众实现。

以上是明确边界与待验证事项；本轮没有发现必须扩大设计才能写出最小方案的问题。F06B 是否能按上述证据条件工作须由下一轮测试确认，不能把设计当作实现完成。

## 5. F06B 只实施一个实验员工详情函数及专项测试

最小文件范围建议：

- 修改 apps/knowledge/selectors.py：上述公共过滤提取，旧公开选择器保留旧发布契约。
- 新增 experiments/wagtail_f06/__init__.py、readers.py、tests.py：单篇员工读取及合成专项。
- 最小修改 experiments/wagtail_f05b/run.py：增加 F06 专项模式，复用现有配置、白名单子进程和内存库防护，明确收集新测试及旧 TestCase 受众回归；不默认重跑全部 F05B 或历史实验。
- 更新本 README。无需新增 settings、模型、迁移、角色或 HTTP 路由。

必要场景以表格为基础，并必须覆盖：

1. 相同 Article 的受众规则在旧选择器与新候选过滤中语义一致；旧选择器仍拒绝旧空指针/错误状态/跨文章指针，新读取可在旧指针为空且 Wagtail 正式证据完整时返回内容。
2. 当前三策略、成员变化、有效期边界、deny、后台身份无绕过；旧 base 过滤/排序/重复行及非法参数契约不回归。
3. 未批准首稿不可读；经批准 V1 可读；V2 草稿/在审/驳回仍返回 V1 的标题/摘要/正文；批准 V2 后切换，V3 草稿不泄露。
4. 下架、归档、空间停用、生效未到，即便 live=True 也不可读；恢复可用条件后重新按当前受众判断。
5. KnowledgeContent 缺失、live=False、空/跨对象/JSON 改绑 live_revision、缺失或错绑批准/提交证据、直发无证据均拒绝；不回填或回退旧内容。
6. 全程只读，调用前后旧 Article（含两个旧指针）、ArticleVersion、ReviewRecord、实验内容、修订及审核记录不变；失败返回不泄露标题/摘要/正文。实验读取不改写 Article.title 或日期。

明确排除：列表、搜索、分页、HTTP 页面/API、附件、正式角色调整、生产切换，以及 PostgreSQL、并发或永久历史机制。不得自动扩展为 F06 后续整套任务。

## 6. 本轮核对与停止点

证据文件：apps/knowledge/selectors.py（46～84、87～145、148～221、224～273 行）、models.py 的 Article/ArticleAudience/枚举；apps/accounts/models.py 的 AccountStatus、UserDepartment、UserGroupMembership；knowledge/configuration.py；test_selectors.py 与 test_selector_boundaries.py 的相关断言；ADR-0002 第 2～4 节；F04A models.py/versions.py、F05A TaskSubmission、F05B services.py 及读取/发布相关测试。

本轮仅源码与文档核对、新文档空白检查；未导入 Django、未运行数据库/业务测试或迁移。未读取真实 .env、安装依赖、操作 Docker 或持久库，未修改主 worktree、暂存、提交或推送。

唯一新增文件为本 README；保留已有 AGENTS.md、角色文件及 ADR/experiments 全部未提交成果。分支和上述 HEAD 不变，暂存区为空。完成后停止，不进入 F06B。


## 7. F06B-1：公共业务可见性提取（2026-09-13）

状态：本小任务完成；前文 F06A 为历史设计，员工详情函数仍待 F06B-2，不在本轮实现。

- 提取 `_audience_eligible_articles(user, *, base=None, now=None)`，位于 apps/knowledge/selectors.py。只过滤业务可见性，不证明存在可读取的正式内容。账号、文章/空间状态、effective_at、三策略、有效部门/内容组、deny 优先均复用原表达式；没有后台身份绕过。
- visible_articles 在公共过滤后无条件追加 current_published_version 非空、status=published、article_id=F("pk") 三项；can_read_article 仍调用 visible_articles(...).exists()。无关闭权限/发布检查的参数。
- _unique_article_base、查询参数校验、去重、排序、数据库别名、时间处理与账号检查顺序未修改。正式模块没有新增 Wagtail 或实验 App 依赖。
- 在 test_selectors.py 原有三个用例内补充证据：空指针、draft 指针、跨文章指针虽能进入业务候选集，visible_articles 和 can_read_article 仍拒绝。未重复建立同名测试或复制受众规则。

本轮文件：修改 apps/knowledge/selectors.py、apps/knowledge/tests/test_selectors.py、本 README；新增 experiments/wagtail_f06/run_audience.py。额外 runner 是验证未启用 Wagtail 时仍可用所需的隔离设施，未改变正式配置。

隔离 runner 使用白名单环境子进程、settings.configure 合成配置，只注册 auth/contenttypes/accounts/knowledge；禁止导入 config、dotenv、wagtail、experiments，禁止读取 .env/正式 base.py、联网及非内存 SQLite。迁移仅用于创建本次内存测试结构，不操作持久库。没有新增迁移。

实际执行：

- 首次 runner 尝试使用 pytest，因现有 .venv 未安装 pytest，在测试收集前停止（执行 0 个测试）；未安装依赖，改用 Django DiscoverRunner。
- 最终 runner 执行一次 test_selectors.py：67 个不重复测试，全部通过；其中三个既有用例增加了上述断言。
- test_selector_boundaries.py 为 pytest 函数，未执行，不计入 67；其中正式配置解析测试也不符合本次隔离范围。其与提取相关的源码契约已核对，但不能替代实际运行证明。
- Django 系统检查无错误，保留 108 条 SQLite 表/列注释警告（0 silenced）。Ruff check、format --check、三份 Python 文件内存编译及本轮差异空白检查通过。首次 Ruff 因缓存写权限失败，使用 --no-cache 后通过。
- 未运行审核发布、全项目或其他历史实验套件；F05B 历史成绩不累计。

PowerShell 复跑（在隔离 PoC 根目录执行）：

```powershell
.\.venv\Scripts\python.exe -I -B experiments/wagtail_f06/run_audience.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache apps/knowledge/selectors.py apps/knowledge/tests/test_selectors.py experiments/wagtail_f06/run_audience.py
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache apps/knowledge/selectors.py apps/knowledge/tests/test_selectors.py experiments/wagtail_f06/run_audience.py
```

最终分支 fusion/wagtail-poc、HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变，暂存区为空。原 AGENTS.md、三个 accounts 角色相关文件、ADR-0002 及已有 experiments 成果保留；本轮只新增/修改上述四个文件。未读取真实 .env、安装依赖、操作 Docker/持久库、修改主 worktree、暂存、提交或推送。完成后停止，等待 F06B-2。


## 8. F06B-2：实验员工正式详情（2026-09-13）

完成入口：readers.get_employee_article_detail(user, article_id)。article_id 接受 Article 的 UUID 或 UUID 字符串；不接受 Article 对象。返回冻结的 EmployeeArticleDetail（article_id、content_id、revision_id、title、summary、body），失败统一 None；没有 ORM、原始 JSON 或隐式旧内容回退。

实际校验条件：

1. 拒绝匿名、非 User、未保存身份；按 user.pk 重新读取当前账号。通过 `_audience_eligible_articles` 从数据库按 Article 主键过滤当前账号、文章/空间状态、生效时间和受众；没有后台身份绕过。
2. 按 Article 的一对一关联查询 live=True 的 KnowledgeContent；live_revision 必须存在。调用 checked_revision 检查 content_type、base_content_type、object_id，并经 with_content_json 检查快照 pk 与 article 关联。title/summary/body 必须存在且为字符串，结果三个内容字段只取该已核验快照。
3. 该正式修订必须恰有一个 status=approved 的 TaskState；任务类型为 RejectOnlyTask，finished_at 和 finished_by 非空。关联 WorkflowState 必须 approved、current_task_state 指向该任务、两个内容类型及 object_id 均与 KnowledgeContent 匹配。
4. TaskSubmission 按 task_state 唯一关联，revision 必须与正式修订/任务一致，submitted_by 存在。修订创建者、提交人、批准者账号记录均存在；批准者不得是创建者或提交人。
5. 不要求 latest_revision 等于正式修订，不检查对象当前有没有新审核，也不重跑要求 in_progress 的批准资格服务。不以历史审核员当前组成员关系、在职状态或当前工作流配置重新授权历史事实。当前读者仍每次重新校验。
6. 仅捕获局部预期的缺失/校验/值类型异常；注入 RuntimeError 会向上传播，不返回虚假成功。读取没有写入、历史修复或旧指针填充；多次 SELECT 不保证并发一致性。

测试数据：本轮新建合成工作流、任务、审核组和三个独立身份，正式数据全部经 F05A submit 和 F05B approve_review 生成。只有“历史直发无证据拒绝”反例使用底层 PublishRevisionAction 直接发布；它不是合法发布夹具，也不是新增业务入口。新草稿、在审、驳回后仍返回同一旧正式快照；审核员离组且离职后仍可读。

实际验证：

- 第一轮 11 项通过；补实际跨对象正式指针与异常 JSON 用例后，最终运行 12 项全部通过。两次共执行 23 次测试，不重复测试数量为 12，不把子测试或此前成绩累加。
- 覆盖旧发布指针为空、三个快照字段隔离、新一轮在审/驳回、无内容/未发布/直发无证据、三种受众策略代表场景、deny、账号失效、下架/归档/空间停用/未来生效、后台身份无绕过、历史审核员离组离职、修订类型/对象/JSON 错绑、批准和提交证据异常。
- 每个正常返回/拒绝的 read 辅助断言比较 Article/ArticleVersion/ReviewRecord、KnowledgeContent/Revision/ModelLogEntry、TaskState/WorkflowState/TaskSubmission 全字段快照，同时要求读取 SQL 全为 SELECT。此证据针对详情函数，不将夹具的构造/故障注入写入算作读取行为。
- Django DiscoverRunner 系统检查无错误；108 条 SQLite 表/列注释警告保留，0 silenced。最终 Ruff check、format --check、三份 Python 文件内存编译、四份本轮文件空白检查通过。初次格式整理前 Ruff 报告的长行和导入排序问题已修正。
- 公共选择器未修改，不重跑 67 项受众历史测试或 F05B 套件；此前 pytest 函数式边界测试继续未验证。没有新增模型/迁移，未运行迁移一致性检查；runner 仅在内存库应用已有迁移以建立测试结构。

完整 PowerShell 复跑命令：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B experiments/wagtail_f06/run_detail.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f06/readers.py experiments/wagtail_f06/test_readers.py experiments/wagtail_f06/run_detail.py
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f06/readers.py experiments/wagtail_f06/test_readers.py experiments/wagtail_f06/run_detail.py
```

run_detail.py 固定使用已核对的 F05B→F02 合成配置链，复用白名单子进程、防止 config/dotenv 导入、.env 文件访问、外部连接及非 :memory: SQLite 的审计防护。未安装 pytest 或其他依赖。

本轮新增 readers.py、test_readers.py、run_detail.py，仅更新本 README。分支 fusion/wagtail-poc、HEAD d59c87c660807d80e78727da3c25222c98e606dd 未变，暂存区为空；此前 AGENTS、角色、公共选择器及测试、ADR 与实验成果均保留。未修改主 worktree、正式模型/配置/角色，未读取真实 .env、操作 Docker/持久库、暂存、提交或推送。

本轮仅验证实验详情函数，尚未完成员工 HTTP 访问接入、PostgreSQL、并发或永久批准证据保留。没有列表、搜索、页面或正式读取路径切换；完成后停止。


## 9. F06C：实验员工详情 HTTP（2026-09-13）

完成：仅 F06 合成配置注册 `GET /experiments/f06/articles/<article_id>/`，路由名 f06_article_detail。路径参数使用 str converter，UUID 解析仍由已有详情函数完成；非法 UUID 因此也返回统一 JSON 404，不复制输入或业务校验。正式 config/urls.py、F05B 配置和既有路由未修改。

认证继续使用 SessionMiddleware、AuthenticationMiddleware 与 AccountStateBackend；普通有效员工不需要 is_staff 或 wagtailadmin.access_admin。视图通过认证后只调用 get_employee_article_detail(request.user, article_id)，没有模型查询、受众判断或批准逻辑副本。

响应契约：

- 200：白名单 article_id（UUID 字符串）、content_id、revision_id、title、summary、body；用 JsonResponse 编码，不信任正文为 HTML。实测带脚本字样、引号与换行的正文仍是 application/json 文本，且有 nosniff。
- 未登录 GET：401，固定 `{"error": "authentication_required"}`，不调用详情函数；无会话请求实测零数据库查询。
- 详情返回 None：404，固定 `{"error": "not_found"}`。不存在、无权、未发布、缺批准证据响应体相同。
- 已有会话对应账号 is_active=False、account_status=disabled/departed：认证后端不恢复用户，实际返回上述 401，不查询目标内容。
- 非 GET：视图返回 405，Allow: GET；原 CSRF 防护保留，缺有效 CSRF 的 POST 在中间件层先返回 403。HEAD/OPTIONS/PUT/PATCH/DELETE 也不开放。未声称 CSRF 403 为 JSON。
- F06 路径响应统一 Cache-Control: private, no-store。专用中间件置于既有中间件链外层，覆盖正常、认证/权限拒绝、非法 UUID、方法及 CSRF 拒绝响应，仅作用于 /experiments/f06/articles/ 前缀。没有加入共享缓存，也不代表系统整体缓存安全设计完成。

本轮新增：views.py、urls.py、settings.py、middleware.py、test_http.py、run_http.py；更新本 README。settings.py 仅继承 F05B 合成配置，替换 ROOT_URLCONF 并加入限定路径的缓存响应中间件；既有 readers.py、公共选择器、run_detail.py、F05B/正式配置均保持不变。

实测：一次运行 21 个不重复测试全部通过（9 HTTP + 12 详情回归），未重复收集继承测试。HTTP 用例复用 F06B-2 真实 submit/approve_review 发布夹具，使用 Client(enforce_csrf_checks=True) 和真实密码登录建立会话。验证了无后台权限员工、匿名零查询、相同 404、V2 正式/V3 草稿隔离、会话账号失效、受众撤销、文章下架、超级管理员无绕过、非法 UUID、非 GET、字段白名单、JSON 编码、缓存头，以及仅 F06 注册路由。

请求前后比较业务/修订/任务/发布日志及 Session 全字段快照，并断言请求 SQL 仅 SELECT；登录和故障注入在请求测量外进行。Django runner 系统检查无错误，保留 108 条 SQLite 表/列注释警告，0 silenced。六份新增 Python 文件 Ruff check、format --check、内存语法编译及七份本轮文件空白检查通过。

完整 PowerShell 复跑命令：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B experiments/wagtail_f06/run_http.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f06/views.py experiments/wagtail_f06/urls.py experiments/wagtail_f06/settings.py experiments/wagtail_f06/middleware.py experiments/wagtail_f06/test_http.py experiments/wagtail_f06/run_http.py
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f06/views.py experiments/wagtail_f06/urls.py experiments/wagtail_f06/settings.py experiments/wagtail_f06/middleware.py experiments/wagtail_f06/test_http.py experiments/wagtail_f06/run_http.py
```

runner 固定使用 experiments.wagtail_f06.settings，沿用白名单环境、真实配置/.env 导入与访问防护、外部连接及非内存 SQLite 拒绝机制；没有依赖安装、服务器或持久库操作。此前 pytest 边界用例仍未验证；没有重跑 67 项受众组合、审核发布全套或全项目套件。

最终 fusion/wagtail-poc、HEAD d59c87c660807d80e78727da3c25222c98e606dd 不变，暂存区为空。既有未提交成果经文件哈希核对保留；只有上述六个新文件及 README 属于本轮变化。未修改主 worktree、模型、迁移、角色或正式配置，未暂存、提交或推送。

本轮仅完成实验员工详情 HTTP 接入；正式部署、浏览器交互、PostgreSQL、并发及永久批准证据保留未验证。没有列表、搜索、附件或正式业务读取切换。完成后停止。


## 10. F06D：融合实验本地检查点（2026-09-13）

本次明确授权将已审查的 F01～F06 成果保存为一个本地提交，不推送、不合并 main。提交前基线为 fusion/wagtail-poc / d59c87c660807d80e78727da3c25222c98e606dd，暂存区为空；前文各阶段的未提交状态和停止点是当时记录，本节更新当前检查点状态。

已完成实验环境与账号接入、显式角色配置档、内容修订与后台编辑、审核提交/驳回/重提、禁止自审及受审修订批准发布、公共受众过滤、实验员工正式详情函数和 GET JSON 接口。原正式读取路径尚未切换，没有生产数据迁移或正式部署。

检查点范围为 89 个文件：F01 设计与规则 2；共享角色/同步命令 3；共享受众选择器及测试 2；F02 6；F03A 6；F03B 8；F04A 11；F04B 9；F05A 16；F05B 15；F06 11（含本 README）。按实际文件内容与各阶段 README 确认归属，不以数量或哈希代替范围审查。包含四份实验迁移及其包文件，不包含正式模型/迁移变更。

本轮仅执行文件归属、完整候选及暂存差异审查、敏感信息/非交付文件检查和差异空白检查；按明确文件清单暂存，不使用 git add . 或 git add -A。不重新执行历史业务测试、系统检查或迁移检查。此前各阶段 README 中的成绩仅为历史报告，例如 F05B 最终 45 项、F06B-1 67 项、F06B-2 12 项、F06C 21 项，不合并累计为本轮通过数量。虚拟环境、缓存、运行日志、数据库和真实 .env 不纳入检查点；不读取真实 .env。

PostgreSQL、并发、永久批准证据保留、正式角色内容权限、正式部署及浏览器交互仍待验证；此前 pytest 边界测试未执行的限制保留。本检查点不等于生产上线许可或完整平台安全验收。

提交标题：feat(fusion): 保存Wagtail审核发布与员工详情实验检查点。实际提交哈希以 Git 记录及本轮最终报告为准，避免文档自引用哈希。该提交包含实验代码及共享代码改动；代码回退会撤销对应能力，但不会自动恢复数据库、配置或角色数据。若以后已应用实验迁移或产生数据，须另行制定并授权回退方案，本轮不执行任何回滚。

本轮不新增功能、不重构、不操作主 worktree、Docker 或数据库，不安装依赖，不 fetch/pull/push，不进入 F07。
