# F07A：旧内容迁移映射设计

日期：2026-09-14。基线：fusion/wagtail-poc，HEAD e85592a5024c59837f32ba525a556c954791a601；执行前工作区干净、暂存区为空。

结论：下一步仅演练“原记录保留、来源可追踪、旧内容导入为未发布修订”。不把旧 published 状态转换成新批准资格，不伪造 Wagtail TaskState、WorkflowState 或 TaskSubmission。F06 读取条件保持不变；迁移本身不使旧内容在新员工入口可读。重新发布必须另经真实提交及批准。

## 1. 实际来源与最小映射

现有表为 knowledge.Article / kb_article、knowledge.ArticleVersion / kb_article_version、knowledge.ReviewRecord / kb_review_record。目标目前是实验 fusion_f04a.KnowledgeContent（未指定 db_table，按默认规则为 fusion_f04a_knowledgecontent）及 wagtailcore.Revision；不是已经确定的正式 knowledge.KnowledgeContent。

| 来源字段或状态 | 最小映射与保留方式 | 无法直接映射或必须核对的事项 |
| --- | --- | --- |
| Article.id、kb_no | 原 UUID、KB 编号及 Article 行不变；新 KnowledgeContent 使用自己的 BigAutoField，通过 article 一对一关联原 Article | 不把 UUID/编号改成 Wagtail 内部 ID，不另造 Article；已存在目标且无本批来源映射时拒绝接管 |
| Article.space、category、article_type、owner | 留在原 Article，组织关系与负责人不复制、不重分配；原空间、分类记录不变 | 校验 category.space_id 与 space_id 一致；不按名称猜组织归属，不把 owner 当作版本作者 |
| Article.audience_policy、ArticleAudience 全部规则 | 原样保留，仍由公共受众过滤解释 all_employees/it_only/restricted、成员有效性及 deny 优先 | 不迁移成 Wagtail 审核组或后台权限；账号、部门和业务用户组关联不变，后台身份无阅读绕过 |
| Article.article_status | active/offline/archived 原值不变 | 即使将来有 live 内容，offline/archived 仍拒绝员工读取；迁移不自动上架 |
| Article.title | 保留旧主记录值，记录与旧正式版本标题是否一致 | 新内容标题只取对应 ArticleVersion.title；有差异记录冲突，不静默同步主记录或以其覆盖版本标题 |
| Article.created_by、updated_by、created_at、updated_at | 保留原字段；来源快照同时记录 | 不把主记录最后修改人当作版本作者、提交人或审核人；不保存 Article 以免 auto_now 改写 |
| ArticleVersion.title、summary | 原值进入对应新修订 title、summary；长度上限由旧 60/500 到实验 255/TextField 无需截断 | 不补用 Article.title；缺失、非法类型或其他不合法数据拒绝该篇，不截断修复 |
| ArticleVersion.body（JSONField） | 权威结构原样保留于旧记录及来源快照；F07B 仅做 JSON→TextField 可逆编码（UTF-8、ensure_ascii=False、sort_keys=True、固定 separators），解析回 JSON 必须等于原值 | 实验 body 是 TextField，不是 StreamField；编码文本仅用于无损映射演练，不宣称富文本渲染/编辑兼容。未知结构不删节点、不退回 body_plaintext，正式转换另定 |
| applicable_scope、body_plaintext、change_summary | 三字段完整保存在来源快照并保留旧行，明确绑定旧版本 UUID 和目标 Revision ID | 现有 KnowledgeContent 无这些字段；不藏入标题/正文、不冒充 Wagtail 日志 comment。body_plaintext 是派生值，不能代替权威 body；适用范围不能代替受众规则 |
| ArticleVersion.id、article、version_no、status | 映射账目保留源版本 UUID、所属 Article、业务版本号及原状态；另记录目标内容/修订 ID | Revision.pk 不是业务 version_no，不能假设自增连续或两边 ID 相同；Wagtail Revision 没有旧五状态同名字段 |
| Article.current_published_version | 源指针原样保留；核对非空、归属本篇、状态 published，映射其 UUID 到一个未发布导入修订 R1 | 不设置新 live_revision、不调用发布；旧正式标志仅作为 source_status/source_pointer_role 来源事实 |
| Article.latest_working_version | 保留原指针；核对归属及 draft/in_review/rejected 合法状态；指向的版本最后导入为 R2，使目标 latest_revision 指向 R2 | 不凭最大版本号推断工作指针；in_review/rejected 仅保留来源标签，新侧不伪造进行中或驳回任务 |
| 其他历史 ArticleVersion | 旧版本全部保留，不能全部标为 published；未来若需映射更多版本，按明确清单创建不发布的快照并记录原状态 | superseded 不是新的发布证据；非指针历史、额外版本、未知状态不纳入 F07B，输入超范围明确拒绝，不静默忽略 |
| ArticleVersion.created_by、created_at、updated_at | 原作者账号 ID 和原始时间均保留来源；导入 save_revision(user=源 created_by) 明确表示来源作者归属，另记真实迁移操作者与导入时间 | 不根据 owner/updated_by 猜作者；账号缺失拒绝。Revision.user 是上游动作用户字段，这里是显式迁移归属，不声称原作者执行了本次导入；不得借此制造提交/批准。新 Revision.created_at 保持实际导入时间，不回填伪造旧操作时间 |
| ArticleVersion.submitted_by、submitted_at、published_at | 保留精确源值（含空值与时区），记录在该版本的来源快照 | submitted_at 注释表示首次或最近提交，不能推导多轮身份。旧 submitted_by 不是新 TaskSubmission；旧 published_at 不填新 first_published_at/last_published_at |
| ReviewRecord 全字段 | 保留 id、article_version、review_type、reviewer、decision、comment、reviewed_at 及原记录；来源快照按记录 UUID 明确列出并绑定版本 | 不改写成新任务，不将 reviewer 填作新 finished_by；不重建 reviewed_at（auto_now_add）。审核人当前权限变化不改写历史事实 |
| Article.effective_at、review_due_at | 仍沿用现有 Article 归属：effective_at 为空或 <= 服务端 now；review_due_at 保留，不自动令文章失效 | 不迁移到 go_live_at/expire_at、不重新设计日期。新 go_live_at、expire_at、approved_go_live_at 不从旧日期推导；当前 F05B 仅支持即时发布 |

来源快照是下一步拟增加的最小实验映射记录概念，不是当前已存在的字段或永久批准凭证。须保存上述所有源字段与完整审核记录列表，不只存摘要/hash；原表仍为历史来源。JSON 数字/空值/Unicode 必须语义等值，UUID 与时间采用明确类型编码；若无法无损表示，停止本篇导入。内容展示与富文本模型改造均不属于本轮。

## 2. 为什么不能由 published 推断批准完整

源码证据：

- ArticleVersion 的条件唯一约束仅限制每篇最多一个 published、最多一个 draft/in_review/rejected；CHECK 要求非 draft 有 submitted_by/submitted_at，published 有 published_at。没有“必须有批准 ReviewRecord”的数据库约束或 clean 校验，也没有审核/提交/发布时间顺序约束。
- ReviewRecord 外键指向版本，保存审核类型、结论、审核人、意见和时间。类型实际为 content_review/periodic_review/emergency_review；结论为 approved/rejected/continue_valid/revision_required/offline。模型不约束类型和结论组合，continue_valid 不能自动当作首次发布批准，紧急审核也不能自动成为本轮自审例外。
- ReviewRecord.clean 只排除 reviewer == version.created_by，未排除提交人；自审不是数据库约束。test_models.py 的 test_author_self_review_is_not_a_db_constraint 明确记录直接 create 可写入自审记录；make_published_version 也不创建审核记录。本轮只读这些测试源码，没有执行。
- 没有审核轮次绑定、当时审核组授权快照或受审内容不可变指纹。多条记录的先后不能只取“最近 approved”猜最终结论；版本 updated_at、submitted_at 不能证明审核后未修改或哪轮提交被批准。

若以后考虑“迁移批准凭证”，最低限度应验证：当前正式指针与版本归属正确；同一内容快照有明确 content_review/approved 记录；作者、提交者、审核者来源明确且审核者不同于前两者；created/submitted/reviewed/published 时间链合理；没有未解释的驳回、下架或相互矛盾记录；另有可信来源证明当时授权及审核后内容未变。凭证须绑定源版本/审核记录 ID、完整来源快照、转换规则版本、源/目标内容摘要、目标对象/修订和受控核验决定，不能靠备注“已迁移”或 status=published 授权。

当前模型字段即使表面齐全，也不能单独证明上述最后两项；本轮未查真实数据，不能宣称所有历史数据都缺证据或都足够。最小选择是：F07B 不建立迁移批准凭证，不走历史批准自动承接分支，所有导入内容保持未发布。完整旧审核记录仍用于追溯，绝不伪造 Wagtail 任务来满足 F06。

将来如有足够外部可信证据，迁移批准凭证可作为另行设计的来源类型，但须独立授权其验证规则、保留措施及读取适配；当前 F06 不识别这种凭证，不能仅新增一条记录就认为可读。本轮不放宽 F06、不实现永久证据体系。

## 3. F06 读取与重新审核边界

F06 需要 live=True、正确 live_revision（类型、对象、JSON 的 pk/article 均一致）、该修订唯一 approved TaskState、approved WorkflowState 且其 current_task_state 指向该任务、有效且同修订的 TaskSubmission、完成时间与三个身份记录存在、批准者非作者/提交人。它不检查历史审核员现在仍在组内，但会重新检查当前读者账号和受众。

导入后的 R1、R2 没有这些新批准证据，KnowledgeContent.live=False、live_revision=None，F06 函数应返回 None、HTTP 应返回既有统一 404；不是迁移失败。旧 visible_articles/can_read_article 仍按原指针及 published 状态工作，旧受众和可用性条件满足时仍可读旧正式版本。迁移不切换原读取路径，不建 new-or-old 回退。

需要新侧正式可读时，必须对选定当前草稿走真实 submit/approve_review，提交者由本次服务端认证用户产生，审核人满足新资格。若要重新审核导入旧正式版本 R1，而 latest_revision 已是较新工作草稿 R2，不能直接把 R1 当当前草稿发布；需明确选择并追加新待审修订，保留 R2，另行处理工作稿安排。本次 F07B 不做该流程，不悄悄替用户选择丢弃新工作稿。字段语义/富文本转换未验收前不把导入 JSON 文本用于正式发布。

## 4. F07B 单篇合成演练

只使用隔离配置与 SQLite 内存库：一篇 Article A，旧正式版本 P（version_no=1、published），较新工作草稿 D（version_no=2、draft），P 至少一条明确 content_review/approved 的合成 ReviewRecord Q，身份与时间有序、审核人与作者/提交者不同。这些夹具只说明旧记录字段完整，不假称提供当前模型没有的授权或不可变性证明。

预期映射：

| 源标识 | 新标识（运行时生成，不能预设） | 导入后的含义 |
| --- | --- | --- |
| A.id / A.kb_no | C.pk；C.article_id=A.id | 仅一条 KnowledgeContent；A 及两个旧指针不变 |
| P.id / version_no=1 | R1.pk，Revision 对象身份属于 C | 来源为旧正式版，但新侧未发布；保留 P 的全部字段和 Q 来源 |
| D.id / version_no=2 | R2.pk，Revision 对象身份属于 C | 追加在 R1 后；C.latest_revision_id=R2.pk、has_unpublished_changes=True |
| Q.id | 仅来源映射引用/快照，不创建新审核 ID | 没有导入生成的 TaskState/WorkflowState/TaskSubmission |

C.live=False、live_revision=None；两个新快照的 pk/article 必须来自 C/A，而非把旧版本 UUID 填入快照 pk。R1/R2 的标题摘要分别等于 P/D；body 经反序列化分别等于源 body。其他未直映字段必须在来源快照逐字段可核对。全部旧 Article、ArticleVersion、ReviewRecord、受众及组织数据保持不变。

为跨调用幂等，下一步需要最小实验映射账目（名称和模型仅为建议，F07A 不创建）：按源 Article 唯一记录目标 C 与转换规则版本；每个源 ArticleVersion UUID 唯一绑定一个目标 Revision，目标 Revision 也唯一。记录源完整快照、审核记录列表、来源摘要、目标快照摘要、导入操作者及时间。它只证明导入来源，不保存独立审核状态，不提供批准权限；实验存储/迁移仅在 F07B 明确授权后实施，不增正式模型或永久历史机制。

- 重复执行：同一 A/P/D、相同源字段/审核记录集合及转换版本时，校验已存映射、目标关联和内容摘要，返回同一 C/R1/R2，不再 save_revision；不能只按标题、版本号、latest_revision 或内存变量判断。源变化、目标变化、版本清单变化或无映射的既有内容均明确冲突，不覆盖、不重新导入。摘要不能替代完整来源。
- 原子性：预检后在同一明确 atomic 事务内重新核对源、创建 C、R1、R2 和映射记录；任一失败全部回滚。注入点选 R1 及其映射写入之后、R2/最终映射完成之前，验证无残留目标或映射、旧表不变，移除异常可重试。自增序列出现间隙不算回滚失败；不宣称 atomic 等于并发安全。
- 最小验证：成功的双修订及完整来源映射、旧新读取结果、第二次执行不新增、源或目标不一致时拒绝、一次中途异常完整回滚。故障/重试用例可重建同样单篇夹具，不增加真实批量导入。
- 严格输入：只有上述两版本和明确列出的审核记录；指针跨文章、状态不符、字段缺失或意外额外版本时整篇拒绝，报告字段/原因但不自动修复。未知数据不能通过“草稿兜底”绕过归属或内容完整性检查。

## 5. 未决项与生产边界

正文正式结构、applicable_scope 等受审字段的正式模型位置尚需确定；本设计仅用可逆文本编码和来源快照避免演练丢字段，不是正式内容格式决策。旧审核证据没有可信外部补证时采用重新审核；将来是否引入迁移批准凭证及其信任来源须另行决策。

ADR-0002 的候选日期投影及正式模型归属仍是切换目标，当前实验继续保留 Article 日期。正式 KnowledgeContent 的 App label、表名及迁移依赖图尚未确定；当前 fusion_f04a 和 Wagtail 表结构只能证明实验映射逻辑，不能作为生产迁移脚本直接使用。PROTECT/外键及现有日志不等于永久证据保留。

不扩展附件、搜索、通知、钉钉、批量真实数据、HTTP 改造或正式切换。F07B 只做上述单篇导入演练，不自动发布或重做历史审核。

## 6. 本轮核对

已对照 AGENTS.md、ADR-0002 第 2～5 节、F06 README、apps/knowledge/models.py 的 Article/ArticleVersion/ReviewRecord 字段及约束、test_models.py 相关夹具/自审断言、selectors.py、F04A models.py/apps.py/versions.py、F06 readers.py，以及现有 .venv 中 Wagtail Revision/save_revision 的赋值语义。均为只读源码核对，未导入 Django 或连接数据库。

本轮只新增本 README，并检查新文档空白；不运行业务测试、系统检查或迁移，不读取真实 .env、不安装依赖、不操作 Docker、持久库或主 worktree、不暂存/提交/推送。最终分支及 HEAD 保持上述基线，暂存区为空，新增未跟踪 experiments/wagtail_f07/README.md。完成后停止，不进入 F07B。


## 7. F07B-1：旧版本内容可逆转换（2026-09-14）

状态：纯数据模块及专项完成；F07A 原设计保留，单篇双修订导入尚未执行。

入口位于 conversion.py：

- convert_version(version, reviews) → {format, content, source}；restore_version(converted) → (version, reviews)。
- encode_body(body) → str；decode_body(encoded) → 原 JSON 值。
- ConversionError 为 ValueError 子类，明确拒绝不支持格式、字段缺失/未知、关联错误、损坏编码；错误消息不包含正文或凭据。

格式版本：外层 opsai.legacy-version/1；正文 opsai.legacy-body/1。正文是带 format、payload、sha256 的 JSON 文本。payload 采用 ensure_ascii=False、sort_keys=True、固定 separators、allow_nan=False；SHA-256 基于 payload 的规范 JSON UTF-8 编码，用于发现意外损坏，不是签名、授权或历史批准证明。检测重复 JSON 键、未知格式、非法 JSON 和摘要不一致；不使用 str(dict)、eval 或 pickle。

输入契约为普通 Python 数据，不接收 ORM 对象。version 必须完整提供 ArticleVersion 的 values() 字段形状：id、article_id、version_no、status、title、summary、applicable_scope、body、body_plaintext、change_summary、created_by_id、submitted_by_id、submitted_at、published_at、created_at、updated_at。reviews 必须显式提供列表（可为空），每条含 id、article_version_id、review_type、reviewer_id、decision、comment、reviewed_at。审核版本关联必须一致，不接受重复记录 ID；不猜测缺少审核信息。空列表不表示审批完整。

| 输出分区 | 实际保存内容 |
| --- | --- |
| content | title、summary 原字符串；body 为上述带版本标识的中间编码 |
| source.version | 除 title/summary/body 外的所有旧版本字段，包括 UUID、版本号/状态、适用范围、派生纯文本、版本说明、原作者/提交者及原始时间 |
| source.reviews | 完整审核记录列表，包括审核人、原始时间、结论与意见，保留列表顺序 |

还原合并内容和来源，正文解码后恢复原值。没有源字段被忽略；任何未知字段报错，防止未来模型增加字段后静默丢失。不新增导入人/导入时间字段，不把旧 submitted_by 或审核记录转换为 TaskSubmission、WorkflowState/TaskState 或 live。将来的实际导入操作者、导入时间必须由导入层独立记录。

可逆边界：

- 在支持输入范围内，恢复结构、值和 Python 数据类型；区分 bool/int/float，保留 -0.0 符号、列表顺序、嵌套结构、中文、换行、引号、反斜杠。字典键排列和数据库未保留的原始 JSON 空白不承诺恢复，也不保留可变对象共享引用关系。
- body/applicable_scope 接受标准 JSON 值：字符串键 dict、list、str、int、有限 float、bool、None。None 表示 JSON null，不据此允许 null=False 字段的 SQL NULL。空字典/列表/字符串及嵌套 null 保留；文本字段保持字符串，不以空串替换 None。当前转换保留已取得的空文本值，不充当模型 full_clean 或完整业务合法性校验。
- 来源的版本/文章/审核 ID 要求原生 UUID；账号 ID 是正整数（拒绝 bool）；时间要求原生 datetime 并带 datetime.timezone 或 zoneinfo.ZoneInfo，保留时区信息与 fold，草稿的 submitted_by_id/submitted_at/published_at 可以为 None。无时区时间、UUID/日期字符串不会被猜测转换；提取层若提供其他类型须明确适配后再调用。
- source 通过深拷贝保持原生 UUID/datetime，因此转换结果是内存纯数据对象，不保证直接 json.dumps 或存入 JSONField。F07B-2 如持久化映射，须另定明确 UUID/时间类型编码及对应验证，不能采用 default=str 造成类型丢失；这是尚未实现的边界。
- tuple/set/bytes/Decimal/自定义对象、非字符串 JSON 键、NaN/Infinity、孤立代理字符、循环或超深结构等明确拒绝，不强制字符串化。超出 Python JSON 数值/递归处理能力同样报 ConversionError。
- 正文编码只用于迁移中间表示，不是最终员工正文或编辑器格式；未修改 F06 读取、渲染器或编辑器。本轮不核定旧审核结论的授权真实性，不将 published 当作新批准。

本轮验证：一次执行 9 个 unittest 方法，全部通过（子测试不另计）。涵盖一份旧正式版和较新草稿的往返、嵌套特殊字符与类型、旧来源和时间、确定性及深拷贝、缺失/未知字段、损坏格式/摘要、未知版本及不支持输入。运行器禁止 Django/Wagtail/业务配置/数据库驱动导入，并审计拒绝 .env、SQLite 连接及外部网络；本轮未加载框架、创建内容或连接数据库。

三份 Python 文件 Ruff check、format --check、内存语法编译及本轮四份文件空白检查通过。没有执行 Django 系统检查、迁移检查或历史业务套件（本轮没有 Django 代码/模型变更）。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f07/run_conversion.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f07/conversion.py experiments/wagtail_f07/test_conversion.py experiments/wagtail_f07/run_conversion.py
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f07/conversion.py experiments/wagtail_f07/test_conversion.py experiments/wagtail_f07/run_conversion.py
```

本轮新增 conversion.py、test_conversion.py、run_conversion.py，仅追加更新本 README。最终分支 fusion/wagtail-poc、HEAD e85592a5024c59837f32ba525a556c954791a601 不变，暂存区为空；F07 四份文件未跟踪，既有已提交文件未变。未读取真实 .env、安装依赖、操作 Docker/数据库或主 worktree，未暂存/提交/推送。完成后停止，等待 F07B-2。


## 8. F07B-2：单篇双修订首次导入（2026-09-14）

已完成合成数据首次导入；本节记录实际实现，前文 F07A 的完整重复执行及异常注入方案留到 F07B-3。原三份转换代码保持原样。

入口：`import_service.import_article(article_id, actor)`，返回只含 `content_id` 和顺序 `revision_ids=(R1, R2)` 的 ImportResult。仅供受控实验内部调用，无 HTTP 或正式角色授权入口；从数据库重新取得有效导入账号、Article 指针及其所有 ArticleVersion、ReviewRecord，不接受客户端版本归属。必须恰有两个版本：指针指向本篇 published 版本 P 和版本号更大的 draft 版本 D；分类与空间必须一致。缺失、跨文章、额外版本、无效账号均明确拒绝。

| 旧记录 | 新记录 | 保留方式 |
| --- | --- | --- |
| Article A、旧正式版本 P | 同一个 KnowledgeContent C 的 R1 | convert_version 后保存 title/summary/编码 body，来源绑定 P→C/R1 |
| 同篇较新工作草稿 D | C 的 R2，latest_revision 指向 R2 | 同样转换并保存，来源绑定 D→C/R2 |
| 原作者、提交人、原时间及 ReviewRecord | source_data 内完整转换结果 | 反序列化后 restore_version 恢复版本及审核字段，不生成批准事实 |
| 本次导入人及时间 | Revision.user/created_at 和 imported_by/imported_at | 使用真实导入账号、当前保存时间，不冒充历史操作 |

本节采用当前任务明确要求的 `save_revision(user=importer, log_action=True)`，取代 F07A 中使用原作者的初步建议；原作者只作为来源保留。R1/R2 均未发布，C 保持 live=False、live_revision=None、存在未发布更改；没有 WorkflowState、TaskState 或 TaskSubmission。原 Article、受众、旧发布/工作指针、ArticleVersion 和 ReviewRecord 不写入。正文仍为迁移中间表示，F06 读取条件未变，员工详情返回 None。

新增实验模型 `fusion_f07.ImportedVersionSource` 及 `0001_initial`：source_version 和 revision 分别为 OneToOneField（数据库唯一约束），另保存 content 外键、conversion_format、source_data JSONField、imported_by 外键及 imported_at。关联使用 PROTECT，但不宣称永久历史保留。没有修改正式模型或既有迁移。

来源编码接口 `source_codec.serialize_source` / `deserialize_source`，格式 `opsai.typed-source/1`。source_data 存储整个转换结果（其内部转换格式仍为 opsai.legacy-version/1），确保无需依赖后来变化的目标字段即可还原。每个节点均有类型封装：scalar、list、dict、uuid、datetime；字典编码为键值对列表，正常字典或列表中即使出现相同标记也不会被误认。UUID 恢复原生 UUID；datetime 保存 ISO 值、fold 和固定时区/ZoneInfo 描述，恢复原生 datetime 及受支持时区。严格拒绝未知版本、损坏节点、重复键及不支持类型，不使用 default=str、eval 或 pickle。保留结构、值和类型，不保证原 JSON 空白/键排列或对象共享引用。

整个首次导入位于外层 transaction.atomic：先检查并转换两个来源，再创建 C、R1/R2 及各自来源记录。已有目标内容或来源映射立即拒绝，不覆盖、不返回幂等成功。数据库唯一约束已有验证；本轮没有中途故障注入、完整重复执行策略或并发保证。

本轮最终验证：18 个不重复测试全部通过，包括 7 个首次导入/约束/实际迁移测试、2 个来源编码测试及原有 9 个转换回归。来源在 JSONField 落库后重新查询并解码，与旧数据库 values() 全字段和审核记录完全相等，核对 UUID/datetime 类型、两条修订及最新草稿归属、当前导入身份/时间。测试前后比较旧文章/版本/审核、非空受众及工作流记录，跨文章和已有目标拒绝不增加写入。

本轮该组共执行三次：初次 18 通过；补充非空受众夹具时漏填 created_by，7 项在 setUp 失败（其余 11 通过）；改用现有受众夹具后最终 18 通过。上述为同一组的执行次数，不累计为新的测试数量。历史 F07B-1 成绩另见第 7 节。

默认 runner 固定白名单环境及合成配置，仅允许 SQLite :memory:，禁止真实配置/.env/外部连接；真实应用已有及新增实验迁移。Django 系统检查无错误，保留 108 条 SQLite 不支持数据库注释的警告（0 silenced）；迁移一致性显示 No changes detected。相关 Python 的 Ruff、格式、内存语法编译及全部 F07 文件差异空白检查通过。

完整 PowerShell 复跑（第一条 Python 命令已包含全部 18 项、系统检查和迁移一致性，不需再单跑转换回归）：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f07/run_import.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f07
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f07
```

本轮新增 __init__.py、apps.py、settings.py、models.py、migrations/__init__.py、migrations/0001_initial.py、source_codec.py、import_service.py、test_import.py、run_import.py，追加本 README；原 conversion.py、test_conversion.py、run_conversion.py 未修改。分支 fusion/wagtail-poc、HEAD e85592a5024c59837f32ba525a556c954791a601 不变，暂存区为空，F07 共 14 份文件未跟踪，已跟踪文件无差异。

没有连接持久库、读取真实 .env、安装依赖、操作 Docker 或主 worktree，没有暂存/提交/推送。正式模型归属尚未定稿，实验迁移不是生产迁移脚本。仅首次导入演练完成，不宣称完成幂等、异常回滚专项或生产迁移；停止，等待 F07B-3。


## 9. F07B-3：顺序幂等与异常回滚（2026-09-15）

`import_service.import_article(article_id, actor)` 已补齐单篇合成数据的顺序幂等。每次调用先重新取得有效导入账号、Article 的旧正式/工作指针、该文章全部两个旧版本及按主键排序的实际 ReviewRecord，并重新执行 convert_version 和带类型来源序列化；完整前置条件在首次及重复分支一致执行。

只有以下条件全部成立才返回原 ImportResult：目标 Article 恰有一个 KnowledgeContent；P、D 各有且仅有一条 ImportedVersionSource；两个来源 ID 与当前旧指针及版本集合一致；两条来源共同指向该内容和各自存在的 Wagtail Revision；conversion_format 为 opsai.legacy-version/1；source_data 可严格解码，重新规范序列化后与当前源转换结果全量相等；修订的内容类型、对象 ID、快照主键及 Article 关联正确；修订 title、summary、body 与本轮转换结果一致；Revision.user 与首次来源 imported_by 一致。

已存在内容但映射不完整、映射关联其他内容/版本/修订、格式或来源快照损坏、旧版本/审核字段变化、旧指针变化、历史修订内容或身份变化均抛出 ImportRejected（“导入冲突”），不补写、不覆盖、不删除重建。已有无关目标仍拒绝。规范比较使用确定性的 JSON 编码，不使用进程 hash()。重复成功不更新首次 imported_by/imported_at、Revision.user/created_at 或历史修订；后续正常编辑生成的最新草稿、当前对象字段及 latest_revision 保持原样，幂等返回只证明两条原导入映射仍有效。

真实导入继续使用一个外层 transaction.atomic。测试通过 mock 既有 ImportedVersionSource.objects.create 方法分别在以下位置抛出非预期 RuntimeError，生产代码没有故障开关：

1. R1 与第一条来源均已保存后；事务内观察到一条 Revision 和一条来源。
2. R2 已保存、第二条来源尚未保存时；事务内观察到两条 Revision 和一条来源。

两种异常传播给调用方后，KnowledgeContent、两条 Revision、ImportedVersionSource 及相关 ModelLogEntry 均与执行前数据库快照一致，旧 Article、ArticleVersion、ReviewRecord、ArticleAudience 及审核工作流记录不变。测试未要求自增值连续。移除注入后对同一 Article 重试，两种场景都恰好生成一个内容、两条修订和两条来源；内容仍 live=False、live_revision=None，无 TaskState、WorkflowState 或 TaskSubmission，F06 员工详情仍返回 None。

本轮一次执行 26 个不重复测试，全部通过：15 个导入/约束/幂等/回滚及实验迁移测试、2 个来源编码测试、9 个转换回归。Django 系统检查无错误；保留 108 条 SQLite 不支持数据库注释的警告（0 silenced）。runner 确认仅使用合成配置与 SQLite :memory:，拒绝真实 .env、正式配置、非内存数据库和外部连接；迁移一致性为 No changes detected。本轮没有模型字段变化或新迁移。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f07/run_import.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f07
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f07
```

本轮仅修改 import_service.py、test_import.py、run_import.py 和本 README；来源模型及 0001_initial 不变。分支 fusion/wagtail-poc、HEAD e85592a5024c59837f32ba525a556c954791a601 保持基线，暂存区为空，F07 的14份文件继续全部未跟踪，已跟踪文件无差异。未读取真实 .env、安装依赖、操作 Docker、持久数据库或主 worktree，未暂存、提交或推送。

本轮仅完成单篇合成数据的顺序幂等与事务回滚；未完成并发、批量导入、增量同步、自动修复、重新审核或生产迁移。完成后停止。


## 10. F07C：导入内容重新审核与员工读取联通（2026-09-15）

新增 `test_integration.ImportedReviewReadIntegrationTests`，只验证现有服务与入口的真实组合，不新增业务服务、模型、迁移、后台页面或 URL。合成调用链为：

`import_article(A, importer)` → 已认证编辑账号经现有 Wagtail Snippet edit POST 保存确认稿 → `submit(C, R3, submitter)` → `approve_review(task_id, reviewer)` → `get_employee_article_detail(employee, A)`。

本次合成执行中的标识为 C=1、导入 R1/R2、确认待审 R3、批准任务 T1、批准后新草稿 R4。数字仅是内存测试库本次执行结果，不构成稳定业务编号。

| 阶段 | 正式状态 | 有权限员工读取 | 无权限员工读取 |
| --- | --- | --- | --- |
| 导入 R1/R2 后 | live=False、无 live_revision | None | None |
| 编辑账号通过现有 CSRF Snippet POST 保存 R3 后 | R3 为 latest，仍未发布 | None | None |
| 提交 R3 后、批准前 | 真实 TaskState/TaskSubmission 均绑定 R3 | None | None |
| 合法第三方批准后 | 工作流及任务 approved，live_revision=R3 | R3 的标题、摘要及编码正文 | None |
| 再保存 R4 草稿后 | latest_revision=R4，live_revision 仍为 R3 | 仍为 R3 | None |

编辑账号和本轮提交人都实际属于任务审核组；分别调用 approve_review 仍由现有服务以“受审修订创建者”和“本次审核提交人”拒绝。第三方审核员属于同一实际审核组且不是上述身份，批准成功。TaskSubmission 由 submit 服务在真实工作流启动时创建，没有从旧 ReviewRecord 生成任务、批准身份或 TaskSubmission。

R3 的 Revision.user 是执行 Snippet 保存的编辑账号。R3 正文沿用导入后 KnowledgeContent 中的 opsai.legacy-body/1 迁移中间编码，审批及读取返回同一编码文本；该数据仅证明调用链联通，不是面向员工的可上线正文格式。

测试在导入后保存两条 ImportedVersionSource 及 R1/R2 的完整数据库快照；保存 R3、提交、批准、保存 R4及重复调用 import_article 后，来源行及两条原导入修订均未变化。最终重复导入返回最初的 C/R1/R2 标识，KnowledgeContent 当前字段、R4 latest_revision、R3 live_revision、所有 Revision、TaskState、WorkflowState 和 TaskSubmission 的完整快照均未变化。Article 身份、受众、状态、旧正式/工作指针、两个旧 ArticleVersion 和旧 ReviewRecord 从演练基线到结束保持一致。

本轮一次执行 27 个不重复测试，全部通过：新增 1 个完整集成测试，以及现有 F07 的26项导入、幂等、异常回滚、来源编码和转换回归；runner 标签互不重叠，没有重复收集。Django 系统检查无错误，保留108条 SQLite 不支持数据库注释的警告（0 silenced）；迁移一致性为 No changes detected。合成 runner 只允许 SQLite :memory:，未读取真实 .env 或连接外部资源。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f07/run_import.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f07
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f07
```

本轮新增 test_integration.py，仅调整 run_import.py 的测试收集范围并追加本 README。审核、批准、读取及共享代码均未修改，因此未重复其独立历史套件。分支 fusion/wagtail-poc、HEAD e85592a5024c59837f32ba525a556c954791a601 保持基线，暂存区为空；F07 现有14份未跟踪文件全部保留，加上本轮新文件后共15份未跟踪文件，已跟踪文件无差异。未读取真实 .env、安装依赖、操作 Docker、持久数据库或主 worktree，未暂存、提交或推送。

本轮仅完成合成数据的导入、重新审核与员工读取联通；迁移编码正文尚未完成面向用户的展示转换，不能据此执行生产迁移。


## 11. F07D：迁移演练本地检查点（2026-09-15）

本检查点保存 F07A～F07C 的设计、可逆转换及类型编码、来源模型与实验迁移、单篇双修订导入、顺序幂等、异常回滚及重新审核员工读取联通。原业务记录保留；没有切换正式读取路径。

27项不重复测试通过为 F07C 此前实际执行结果，本轮仅进行文件归属/内容/敏感信息审查、文件空白及完整暂存差异/空白检查，不重新执行任何业务测试、系统检查或数据库迁移。

仅为单篇合成数据的实验节点：编码正文尚未完成面向用户的展示转换，并发、批量导入、PostgreSQL 及生产迁移未验证，不能直接执行生产迁移。

计划本地提交标题：feat(fusion): 完成旧内容迁移与重新审核演练。提交包含本目录15份已确认文件，不推送、不合并 main。回退代码会撤销对应 F07 实验能力；代码回退不会自动撤销数据库迁移或恢复数据，本轮不执行任何回滚操作。
