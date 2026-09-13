# ADR-0002：OpsAI-IT × Wagtail 融合基线与最小设计（F01）

- 状态：方向已确认，模型方案待最小验证
- 日期：2026-09-11
- 授权范围：仅形成设计记录及最小同步项目规则；不安装依赖、不修改业务代码、不迁移、不进入 F02。
- 决策依据：用户本轮授权、V1.1A PRD 第 4.2、8、9 章、模块目录规划、架构与 API 清单第 3.2 节、ADR-0001。

## 1. 本机基线与证据边界

| 项目 | 本机核验结果 |
| --- | --- |
| OpsAI-IT 根目录 | `D:\Desktop\OpsAI\AI-OpsAI-IT`；由 `git rev-parse --show-toplevel` 核验 |
| 分支与完整 HEAD | `main`；`d59c87c660807d80e78727da3c25222c98e606dd`，与用户参考相同，无后续提交需要比较 |
| 初始状态 | 工作区、暂存区均干净；本轮不暂存、提交或推送 |
| OpsAI-IT 版本声明 | `pyproject.toml`：项目 `0.1.0`，Python `>=3.13,<3.14`、Django `>=5.2,<5.3`；这不是本轮解释器或已安装依赖的运行核验 |
| Wagtail 源码目录 | `D:\Desktop\OpsAI\wagtail-7.4.3\wagtail-7.4.3`，目录存在，无需搜索或下载 |
| Wagtail 版本与引用 | `wagtail/__init__.py` 声明 `7.4.3`；直接读取 `.git/HEAD` 得到 `eceb34882b5e45bdf96c29222f574e9a506533a9`，与参考相同 |
| Wagtail 核验限制 | Git 命令因目录所有权检查拒绝执行；未修改 Git 配置。HEAD 为直接读取的元数据，未完成上游工作区与提交内容一致性核验，不声称源码树干净 |
| 第 8J | 检索仓库文档、变更记录及报告文件名，未找到第 8J 实际运行报告：**尚未取得实际运行证据**。不推断 PostgreSQL、持久迁移、注释或并发行为已验证 |

已读取两侧根目录 AGENTS.md、OpsAI-IT README、当前 PRD、两份架构文档及 ADR-0001；数据库参考文件仅作设计参考，正式模型以 `apps/knowledge/models.py` 为准。源码检查为静态定点阅读，不代表执行了相关测试。

关键证据索引（上游路径相对于上述 Wagtail 目录）：

| 证据 | 本轮相关事实 |
| --- | --- |
| `apps/accounts/models.py`、`roles.py`、`management/commands/sync_system_roles.py`、`views.py` | 现有自定义用户及账号状态；角色集中定义；同步调用 `group.permissions.set(resolved)`；模拟登录使用固定身份与开发开关 |
| `apps/knowledge/models.py`、`selectors.py` | 旧发布/工作版本指针有归属和状态校验；员工读取依赖旧版本表；拒绝优先 |
| `apps/knowledge/admin.py`、`forms.py` | Article 新增关闭；版本、审核后台保护；受众联合最终状态校验及非循环保存顺序 |
| `apps/accounts/migrations/0001～0002`、`apps/knowledge/migrations/0001～0003` | 文件存在；版本条件唯一约束、受众约束及注释迁移存在，不证明持久库应用状态 |
| `apps/knowledge/tests/test_models.py`、`test_admin_protection.py`、`test_selectors.py`、`test_joint_admin.py`；`apps/accounts/tests/test_roles.py` 等 | 已有版本归属、自审模型校验、后台保护、角色和受众测试；自审不是数据库约束的测试明确存在；本轮未运行 |
| `config/settings/{base,test,development,production}.py`、`config/urls.py`、`deploy/compose.yaml` | test 导入 base；base 无条件调用 `load_dotenv(BASE_DIR / ".env")`；现有路由无 Wagtail；Compose 固定项目名 `opsai-it` 并加载开发配置 |
| 上游 `wagtail/models/{revisions,draft_state,workflows}.py` | 修订可序列化、覆盖；`live_revision` 与 `latest_revision` 分开；Mixin 顺序有系统检查；默认组审核没有作者排除 |
| 上游 `wagtail/snippets/views/snippets.py`、`wagtail/admin/views/generic/mixins.py`、`wagtail/actions/publish_revision.py` | Snippet 有编辑、发布、历史恢复入口；后台可接收 `overwrite_revision_id`；发布动作不能代替业务审核门槛 |
| 上游 `wagtail/admin/auth.py`、`wagtail/users/models.py` | 后台使用 `wagtailadmin.access_admin`；用户关联支持 `AUTH_USER_MODEL`，不要求统一提高 staff |
| 上游 `wagtail/management/commands/purge_revisions.py`、`pyproject.toml` | 有旧修订清理命令；声明 Python >=3.10、Django >=5.2，分类声明包含 Python 3.13 / Django 5.2；实际安装兼容性待 F02 |

## 2. 决定一：模型与字段归属

OpsAI-IT 继续作为模块化 Django 主项目；Wagtail 以依赖形式提供编辑、Revision 和 Workflow 基础能力。保留 `accounts.User`、组织关系、业务模块边界和 V1.1A 范围，不维护框架分叉，不建立第二套账号。

优先验证 `knowledge.KnowledgeContent`：独立内部主键，通过不可由编辑表单修改的 `OneToOneField(Article, on_delete=PROTECT)` 关联稳定业务身份。候选继承顺序为 `WorkflowMixin, DraftStateMixin, RevisionMixin, models.Model`，后续如需锁或子对象再单独验证。不要把 Article 的 UUID 直接改为 Wagtail 内部 ID；UUID 和 KB 编号继续作为业务及接口标识。Snippet 注册、序列化和模型关系尚未实现。

下表为正式切换的目标职责；F01、F02 均不调整现有字段。

| 字段 | 权威归属与类别 | 写入及读取规则 |
| --- | --- | --- |
| UUID | Article；稳定业务身份 | 不随正文修订变化；恢复历史修订不得替换关联 Article |
| KB 编号 | Article；稳定业务身份 | 保持不可变、唯一、`KB-000001` 格式；编号服务未完成前保持新增入口关闭 |
| 标题 | KnowledgeContent Revision；必须审核 | 正式标题取已批准发布修订；Article.title 若保留，仅为正式标题的只读查询投影 |
| 摘要 | KnowledgeContent Revision；必须审核 | 不在 Article 另建可编辑摘要；搜索只能取正式版本 |
| 正文 | KnowledgeContent Revision；必须审核 | 结构化正文为权威；具体 JSON / StreamField 结构、旧内容转换另行验证 |
| 适用范围 | KnowledgeContent Revision；必须审核 | 随内容冻结、审核和发布；不是内容受众授权 |
| 空间 | Article；业务管理字段 | 不随正文恢复；修改须授权、审计并校验分类归属，立即使用当前启用状态 |
| 分类 | Article；业务管理字段 | 不随正文恢复；与空间保持一致；分类停用不自行改变 ADR-0001 阅读规则 |
| 负责人 | Article；业务管理字段 | 受控移交并审计；审核时记录负责人上下文，正文恢复不得回滚负责人 |
| 文章类型 | Article；业务管理字段 | 保留现有归属；改变模板时必须校验结构化内容，不能用分类操作绕过内容审核 |
| 受众 | Article.audience_policy + ArticleAudience；实时授权 | 保留原管理入口、拒绝优先；历史恢复不得恢复旧授权或扩大当前受众 |
| 生效时间 | 候选 KnowledgeContent.go_live_at；必须随版本审核 | 作为唯一可编辑计划生效时间，发布服务解释；Article.effective_at 若保留，仅投影当前正式修订的值，待审新计划不能隐藏旧正式版 |
| 复审日期 | 候选 KnowledgeContent.review_due_at；审核元数据 | 修订审核或受控复审“继续有效”操作批准后生效，后者必须产生不可变审核证据；Article.review_due_at 仅投影正式值，不从未批准草稿同步 |
| 下架 | Article.article_status=offline；业务可用性 | 立即禁止员工读取；与 Wagtail unpublish 在统一服务事务内协调，保留历史发布证据 |
| 归档 | Article.article_status=archived；业务可用性 | 禁止员工读取和普通再发布；恢复必须新建待审修订并走受控恢复流程 |
| body_text、检索向量、标题/日期投影 | 派生查询字段 | 从正式修订生成，不可独立编辑；不得作为第二份正文或状态来源 |

冗余字段只在成功发布或批准复审的同一事务中更新，并记录来源 Revision ID。切换验收须逐条比对 Article 投影、正式修订字段、来源 ID 和正文提取结果；后续提供只读一致性检查，发现不一致禁止据此扩大读取范围。禁止依赖异步双写维持两套内容。草稿预览单独走管理授权，不更新员工查询投影。

已发现的适配差异：现有 Article Admin 的 title、effective_at、review_due_at 可编辑，而目标是受控投影；现有 PRD 8.3、9.2 使用旧版本指针与状态术语。这里记录候选映射，不宣称已替代 PRD 或完成字段迁移。正式切换前必须另行确认指针表达和日期归属、同步相关设计契约；如无法保持产品语义，停止对应实施并报告，不静默改 PRD。F02 不依赖这些模型决定落地。

## 3. 决定二：版本与可读状态

1. **当前及最小模型验证阶段**：保留现有 ArticleVersion、ReviewRecord、两个版本指针、`Article.clean()` 和 Selector。F02 不创建模型。后续模型试验只用隔离合成数据、专用管理入口；旧员工路径只认旧正式版本，Wagtail 实验修订不伪造旧 published 记录以求可见，不双写、不接入员工路径。
2. **正式切换前**：另行制定历史映射、核对及回退方案，冻结旧写入口；以明确切换点一次切换版本提供方和读取契约。保留旧表和关联以供审计，旧指针转为只读历史信息；不能简单将原外键重指向不同表，也不能只删除旧校验。
3. **新校验契约**：Article 必须恰有一个 KnowledgeContent；`live_revision`、`latest_revision` 必须确实属于该内容对象，核对 Revision 的 content_type、object_id 及关联 Article；不得只检查非空。正式 Revision 还须对应同一修订的有效批准证据；最新修订不等于工作版本，草稿/待审/驳回语义由 Wagtail 修订与工作流映射，不能照搬旧 VersionStatus。模型校验和统一服务共同执行，读取端仍失败关闭。
4. **新员工读取条件**：现有账号门槛、空间启用、Article 为 active、当前受众允许且无 deny，加上 KnowledgeContent.live=True、有效且归属正确的 live_revision、审核批准和生效时间已到，缺一不可。读取正式修订快照，不调用 `get_latest_revision_as_object()` 或“最新修订”接口显示员工正文。新草稿、待审新标题和新日期都不得影响旧正式版。
5. **状态唯一性**：Wagtail 管理修订/审核/发布生命周期；Article 只保留 active/offline/archived 业务可用性，不新增一套草稿审核状态机。任一侧不可读就拒绝；即便 live=True，offline/archived 仍不可读。下架、归档、恢复由统一服务协调；普通 publish 不能自动把 Article 恢复 active。复审到期不直接等于过期或下架，不把 review_due_at 无条件映射为 expire_at。
6. **历史映射**：旧 published/superseded 对应当前/曾正式发布证据，draft/in_review/rejected 对应待验证的工作流视图；不得只凭“存在 Revision”断言已发布。切换前保存旧版本 ID、版本号、作者、时间、内容和审核链映射，核验后再开放新读取。禁止长期维护两套完整状态机。切换后产生新数据时，不能仅回退代码就恢复旧写入，应先停写并按专项回退方案处理。

## 4. 决定三：权限与审核适配

- `accounts.UserGroup` 继续只表示内容受众；Django `Group` 继续表示系统角色。员工阅读不因 staff、superuser、作者、负责人或审核身份绕过 ADR-0001。
- Wagtail 后台每次请求及服务操作都需核对已认证、已保存的现有 User、`is_active=True`、`account_status=active`；将来仍须落实钉钉组织及应用准入。不能只靠后台入口菜单或默认认证后端，禁用/离职后的现存会话也必须拒绝。
- 后台访问使用 `wagtailadmin.access_admin` 和对象操作授权，不统一修改 is_staff。保留模拟登录开关、生产强制关闭、固定身份及无可用密码约束。Wagtail 用户/组管理不能重新开放现有后台禁止的提权入口。
- 所需权限最终统一加入 `apps/accounts/roles.py`，按最小权限设计并验证同步幂等；`sync_system_roles` 会用 `permissions.set` 覆盖手工组授权，不能靠手工勾选维持接入。本轮不改变 0/8/6/19 的现有矩阵，也不预先授予 delete、任意用户/组编辑或直接发布权限。
- 自定义审核任务必须排除当前修订作者自审，并核对当前账号状态、审核资格、目标修订和工作流状态；作者身份需明确持久记录，不能简单把最后保存者当作全部作者依据。上游 GroupApprovalTask 的组成员/超级管理员逻辑不满足该要求。自审限制放在服务和执行动作中，不能只隐藏按钮；现有 ReviewRecord.clean 也不是直接数据库写入的保护。
- PRD 允许受控例外，但现阶段不开放例外；以后如需紧急特批，必须单独落实原因、时限、授权和审计，超级管理员身份本身不是自审例外。
- 后续逐项封堵：直接发布按钮与 POST、历史恢复后发布、定时发布、无工作流/工作流停用、程序调用 `Revision.publish()`、模型 publish、`PublishRevisionAction`、`skip_permission_checks` 及直接 ORM 更新。默认发布权限检查不能证明已审核；修订审批后再编辑不得沿用旧批准。历史恢复先形成新待审修订。
- 候选接入点为 SnippetViewSet/自定义任务/项目服务及 `WAGTAIL_FINISH_WORKFLOW_ACTION`，可行性仍需验证。必须列出所有写入口并让项目支持的入口经过统一服务；不能声称一个 UI hook 或模型 clean 能阻止任意 ORM/SQL 写入。无法封闭的入口不开放上线。
- 定点源码还显示：`PublishRevisionAction.check` 在未传 user 或显式跳过权限时不执行通常的发布权限拒绝；`wagtail/workflows.py` 默认完成动作发布 `get_latest_revision()`。适配必须绑定“本次实际批准的修订”，不能在完成时无条件取最新修订；上述行为是静态代码事实，尚未做项目运行复现。
- 受众继续使用现有 Article Admin/ArticleAudience 管理入口，保留分项权限、最终状态校验、循环交换拒绝和整次回滚。本次不重写 Inline；正式切换仅关闭内容投影字段编辑，保留受众维护能力。

## 5. 决定四：历史保留与事务

- ArticleVersion 和 ReviewRecord 原记录、外键与审核链在迁移完成前全部保留，不删除、不覆盖、不重造虚假历史。正式版本和审核证据长期永久保留；后续新 ReviewRecord 如何关联 Revision 必须专项设计，不能为了沿用旧外键持续生成第二套版本。
- Wagtail `save_revision(overwrite_revision=...)` 会覆盖修订内容和时间；后台存在对应参数入口。融合内容默认禁止修订覆盖，编辑生成新 Revision；至少所有提交审核、批准、曾发布修订不可变。正式上线前还须关闭旧 ArticleVersion Admin 的超级管理员修改/删除旁路。
- 禁止对融合历史运行通用 `purge_revisions`，禁止普通后台单个/批量删除、程序清理或级联删除内容及工作流证据。上游 latest/live 保护不等于永久历史保留；`live_revision` 是 SET_NULL，不能依赖它保护所有曾发布版本。后续验证用 PROTECT 的发布/审核证据引用或等价保留机制，审查 GenericRelation 级联范围；仅取消 delete 权限不足以证明持久保护。
- `apps.workflow` 负责统一服务事务与幂等，调用 Wagtail 能力；`knowledge` 保持业务规则与受众；`audit` 保存不可变操作证据；`dingtalk` 负责通知适配，不另造状态机。
- 批准发布、复审、下架/归档必须在同一数据库、同一 `transaction.atomic()` 边界内写入 Wagtail 任务/修订/发布状态、Article 业务状态和投影、业务审核证据、审计及 Outbox。验证异常时整体回滚、重复请求幂等、同修订审批、状态冲突和并发一致性；atomic 本身不等于锁或并发安全。
- 上游 WorkflowState.finish 有事务及完成动作扩展点，可作为适配候选，不能据此声称 OpsAI 审计/Outbox 已具备事务保证。published/workflow Signal 不承担核心业务写入；`on_commit` 至多唤醒 worker，不能代替持久 Outbox。
- 通知在提交后由 worker 发送，失败记录并幂等重试，不撤销已成功业务操作。Wagtail 自带通知触发也需审查、替换或隔离，避免在业务事务内产生不可回滚的外部发送。本轮不实现审计、Outbox、通知或锁。

## 6. 决定五：F02 环境隔离方案（仅计划）

推荐从经确认的 F01 基线创建独立 worktree；F01 未提交时，不擅自提交或把不明工作区变更带入。F02 开始前记录基线和本 ADR 的取得方式；工作目录已存在则停下核对，不覆盖。

| 隔离层 | 推荐资源及约束 |
| --- | --- |
| 分支与目录 | 分支 `codex/f02-wagtail-compat`；独立工作目录 `D:\Projects\OpsAI-IT-F02`；只带跟踪源码，不复制 .env、.venv、媒体、日志或数据库 |
| Python 依赖 | 独立目录根下 `.venv`，使用 Python 3.13；禁止复用主项目 .venv 或全局安装；所有命令用该目录 `.venv\Scripts\python.exe` 的绝对路径 |
| 配置与凭据 | 新增实验专用 `config/settings/fusion_compat.py`，**独立定义最小设置，不导入 base/test/development/production，不调用 dotenv**；显式指定 settings，使用仅供测试的非秘密值及假数据 |
| 进程环境 | 启动器以环境变量白名单构造子进程，保留运行必需系统变量，显式设置实验 settings；不继承业务 `POSTGRES_*`、钉钉凭据、DJANGO_SECRET_KEY、PYTHONPATH 等；不打印凭据，不把主项目路径加入模块搜索路径 |
| F02 数据库 | SQLite `:memory:` 用于无业务数据的应用初始化及系统检查；不执行迁移、不连接 PostgreSQL。这只证明相应配置启动能力 |
| 后续专用 PostgreSQL | 需要数据库行为验证时另行授权；项目名 `opsai-it-fusion-<批次>`，数据库 `opsai_it_fusion_<批次>`，独立用户及数据卷 `opsai-it-fusion-<批次>_postgres_data`，例如批次 `f03a`；端口另选并先查冲突 |
| 后续 Compose/凭据 | 仅使用专用实验 Compose 和独立临时凭据文件；不复用 `deploy/compose.yaml`、`../.env` 或开发挂载；**禁止使用 `opsai-it_postgres_data`** |
| 清理范围 | 只列入本批次显式创建的 worktree、.venv、实验日志/锁文件及后续专用数据库资源；清理前核对绝对路径和资源名，保留验证报告，遵守重要数据删除确认规则，不使用通配清理或主项目 down -v |

配置隔离验收应在首次 Django 初始化之前完成：静态追踪实验 settings 的导入链；子进程对 dotenv 加载调用设置失败哨兵并检查主项目配置模块未加载，配合文件打开监测，确认没有读取任何真实 `.env`；使用显式 `--settings` 或专用启动器，不直接依赖 pytest 默认配置。记录模块来源位于隔离工作目录，数据库配置为内存库，检查输出不得泄露环境值。

单独覆盖 DATABASES 不能撤销 base 导入时发生的读取；单独建立 .venv 也不能隔离凭据。三类隔离必须分别举证。本轮只阅读加载链，未执行上述验收或创建资源。

## 7. 决定六：F02 的最小范围和退出条件

F02 仅执行环境准备、固定安装依赖、核验 Python/Django/Wagtail 实际兼容性。Python 保持 3.13 系列，Django 限定 5.2 LTS，Wagtail 目标固定 `7.4.3`；在 F02 核对官方发行包来源及元数据，解析后锁定实际补丁版本和全部传递依赖，记录安装结果及 `pip check`，不把本机源码声明当作实际运行结果。

上游声明包括 DRF、django-tasks、modelsearch、Pillow/Willow 等传递依赖；安装框架运行依赖不等于批准独立 REST 架构、异步基础设施或新的搜索方案，不引入 Redis/Celery/Elasticsearch，不安装上游 testing/docs extras。Windows 原生扩展轮子能否安装、解析器是否保留 Django 5.2、既有 accounts.User 与 Wagtail 应用注册能否初始化，均由 F02 实测。

F02 推荐执行顺序：

1. 核对可用解释器、架构、空间、基线和目标目录；准备隔离工作目录与虚拟环境。
2. 增加实验专用依赖输入/锁文件、独立 settings 和最小 URL 配置、隔离启动/检查脚本；完成配置加载隔离检查。
3. 固定并安装依赖；记录 Python 完整版本、Django/Wagtail 实装版本、模块来源及 `pip check` 结果。
4. 用实验 settings 执行最小导入、`django.setup()` 和无需数据库的 Django 系统检查，注册必要上游应用并保持 `AUTH_USER_MODEL=accounts.User`；报告所有失败/警告及影响，不连接开发数据库、不运行完整套件。
5. 产出兼容性报告并停止，不自动创建 Git 提交。兼容性不通过时继续安全排查，不自行升级 Django 主次版本或扩大范围。

预计修改范围仅限隔离分支中的依赖输入/锁文件、实验 settings、实验 URL、隔离验证脚本及结果文档（例如 `requirements/fusion-compat.*`、`config/settings/fusion_compat.py`、`config/fusion_urls.py`、`scripts/fusion_compat_check.py`）。不改业务模型、审核、搜索、受众、业务迁移或主环境 Compose；不创建 KnowledgeContent，不执行数据迁移。

F02 成功只表示所记录环境的依赖与初始化检查通过，不表示 Snippet 模型或 PostgreSQL 融合通过。后续模型最小验证另行授权，必须覆盖：

- 一对一关系、Mixin 顺序、修订序列化及恢复不能改换 Article；结构化正文与 UUID/内部 ID 配合。
- 草稿不泄露、旧正式版继续可读、日期投影和受众变化生效、下架/归档与 live 组合失败关闭。
- 现有用户、非 staff 后台访问、账号禁用、集中角色同步、自审限制和所有发布旁路。
- 历史修订不可覆盖/清理、审核与发布证据永久保留、事务故障回滚及幂等；PostgreSQL 并发另行实测。
- PRD 旧版本术语与新提供方的映射、日期归属、ReviewRecord 后续关联与正式切换/回退方案。

## 8. F01 检查与停止点

本轮只新增本 ADR 并最小修改根 AGENTS.md。事实按本机源码及文档核对；未运行业务测试、测试收集、Django 初始化或数据库验证，不引用历史通过数量作为本轮成绩。交付前检查实际 diff、文档空白及文件范围；不读取真实 .env、不操作 Docker、不安装依赖、不修改上游、不提交/推送或修改 Git 配置。完成 F01 后停止，F02 须由后续明确任务启动。

本轮检查结果：`git diff --check` 通过；新增未跟踪 ADR 另用 `git diff --no-index --check -- NUL <ADR路径>` 检查通过。实际差异仅为 AGENTS.md 和本 ADR，暂存区为空，HEAD 未变；最终工作区包含这两份待审文档变更。
