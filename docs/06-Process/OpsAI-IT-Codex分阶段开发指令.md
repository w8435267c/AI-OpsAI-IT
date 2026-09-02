# OpsAI-IT 故障问答知识库：Codex 分阶段开发指令

> 适用项目：`AI-OpsAI-IT`<br>
> 当前目标：先完成 Django 单体项目骨架与初始化，再按依赖顺序开发 V1.1A 核心试点版。<br>
> 使用原则：一次只把一个步骤交给 Codex；当前步骤验收通过后，才发送下一步。

## 一、使用方法

1. 先在 VS Code 中打开**唯一的正式 Git 仓库根目录**，不要打开存放多个压缩包和副本的外层文件夹。
2. 正式根目录应当包含 `.git`、`README.md`、`CHANGELOG.md` 和 `docs`。
3. 把下面的“第 1 步指令”完整复制给 Codex。
4. Codex 完成后，重点查看它报告的“验证结果”和 `git status --short`。
5. 只有当前步骤全部通过，才继续下一步。若出现失败，把 Codex 的完整报错发给 ChatGPT 分析，不要跳步。
6. 第 1～6 步属于“项目初始化阶段”。做完第 6 步后，才算骨架和核心数据底座完成。

## 二、所有步骤都必须遵守的规则

以下要求已写进每一步的任务边界，首次使用时仍建议让 Codex 特别注意：

- 先读取现有文件和 `git status`，再修改，不能直接覆盖用户文件。
- 以 `产品需求文档PRD-V1.1A-钉钉集成核心试点版-优化稿.md` 为当前需求基线；旧 V1.1 只作背景参考。
- 以 `Django项目模块目录结构.md` 和 `系统架构与API接口清单.md` 为工程与接口基线。
- 采用已确认的 Django 单体方案，不改成 Vue/React 前后端分离，不引入微服务、Kubernetes、Elasticsearch、Redis 或 Celery。
- 当前阶段只实现提示词明确列出的范围，不提前批量开发 91 个接口。
- 不删除需求文档、历史文档、截图或未知文件；发现重复目录时只报告，不擅自删除。
- 不把密码、AppKey、AppSecret、数据库口令或真实公司信息写入代码、日志或 Git。
- 软件和依赖不得全局安装；Python 虚拟环境放在项目目录 `.venv` 中。若项目位于 D 盘，依赖也随项目保存在 D 盘。
- 修改后必须运行与本步骤相关的检查或测试；不能只生成文件后声称完成。
- 不使用 `git reset --hard`、`git clean -fd`、强制推送或覆盖远端历史。
- 验证通过后可以按提示创建**本地提交**，但不得自动推送 GitHub 或 Gitee。
- 如果环境、文档或现有修改互相冲突，先停止并报告，不擅自改变技术方案。

---

# 第一阶段：项目骨架与初始化

## 第 1 步：只读检查项目，确认唯一开发根目录

> 这一条现在就可以复制给 Codex。此步骤禁止改文件。

```text
你现在负责 OpsAI-IT 故障问答知识库的第 1 步：项目只读检查与开发根目录确认。

背景：
- 这是一个面向公司内部员工的 IT 运维知识库。
- 已确定使用 Python 3.13 + Django 5.2 LTS 的单体应用方案。
- 当前文件夹中可能同时存在压缩包、重复项目副本或嵌套的 .git 目录。
- 本步骤只做检查，不进行项目初始化，不安装软件，不修改文件。

请严格执行：
1. 从当前目录开始，用 pwd、rg --files、find（仅在必要时）检查目录结构。
2. 查找所有 .git 目录，并用 git rev-parse --show-toplevel 判断正式仓库根目录。
3. 在候选仓库中检查 README.md、CHANGELOG.md、docs、PRD、Django项目模块目录结构.md、系统架构与API接口清单.md、models.py 是否存在。
4. 在正式候选仓库中运行并记录：
   - git status --short
   - git branch --show-current
   - git log --oneline -5
   - git remote -v
5. 阅读以下文件；若路径不同，先定位再阅读：
   - README.md
   - CHANGELOG.md
   - 产品需求文档PRD-V1.1A-钉钉集成核心试点版-优化稿.md
   - 产品需求文档PRD-V1.1-钉钉集成版.md
   - Django项目模块目录结构.md
   - 系统架构与API接口清单.md
   - 根目录 models.py
   - 已存在的 AGENTS.md
6. 判断哪个目录应作为唯一正式开发仓库；如果存在 AI-OpsAI-IT (4)、解压副本或嵌套仓库，只列出并说明，禁止删除或修改。
7. 识别未跟踪、已修改和重复的文件，尤其保护新版 PRD、架构清单和 models.py。

本步骤禁止：
- 修改、移动、重命名或删除任何文件；
- 创建虚拟环境或安装依赖；
- 执行 django-admin、迁移或测试；
- git add、commit、push、pull、reset、clean；
- 在多个仓库副本中同时操作。

完成后只输出一份检查报告，必须包含：
A. 建议采用的唯一仓库绝对路径；
B. 选择它的证据；
C. 当前分支、最近提交、远端配置；
D. 未提交/未跟踪文件清单；
E. 重复目录或嵌套 .git 风险；
F. 文档优先级（V1.1A 为当前基线）；
G. 第 2 步建议移动或更新哪些文件，但此时不要执行。

完成报告后停止，等待我确认，不要继续下一步。
```

验收条件：

- Codex 明确给出唯一仓库绝对路径。
- 没有修改任何文件。
- 新版 PRD、架构文件和 `models.py` 均已被识别并保护。
- 重复项目副本没有被误当成正式仓库。

## 第 2 步：确立开发基线，归档新增文档

> 只有第 1 步确认正式仓库后再发送。

```text
继续 OpsAI-IT 项目的第 2 步：确立 V1.1A 开发基线并整理文档。本步骤只整理项目规则和文档，不初始化 Django，不安装依赖。

开始前：
1. 先运行 git rev-parse --show-toplevel，确认当前目录就是第 1 步确定的唯一正式仓库；不是则立即停止。
2. 运行 git status --short，保护全部现有修改和未跟踪文件。
3. 重新读取 README.md、CHANGELOG.md、V1.1A PRD、Django项目模块目录结构.md、系统架构与API接口清单.md。

需要完成：
1. 将当前正式 PRD 放入 docs/02-PRD/，保留清晰的 V1.1A 文件名；旧 V1.1 文件保留，不删除。
2. 将 Django项目模块目录结构.md 和 系统架构与API接口清单.md 放入 docs/04-Architecture/。
3. 根目录 models.py 暂时保留原样，留给后续 knowledge App 集成，不要提前改写或删除。
4. 更新 README.md：
   - 当前阶段改为 V1.1A 核心试点版；
   - 明确 Django 单体技术路线；
   - 修正文档链接；
   - 注明代码尚处于初始化阶段。
5. 在仓库根目录创建或更新 AGENTS.md，用中文写入：
   - 项目目标与 V1.1A 范围；
   - 文档优先级；
   - Django 单体目录约定；
   - apps 的职责边界；
   - 安全、测试、Git 和密钥管理规则；
   - 每次只实现当前任务，禁止越界开发。
6. 更新 CHANGELOG.md 的“未发布”部分，记录本次开发基线整理。
7. 检查所有 README 文档链接都能指向存在的文件。

约束：
- 不删除历史资料或重复副本；重复副本只报告。
- 不修改 PRD 正文、模型业务规则和 API 清单内容。
- 不创建 manage.py、config、apps 或虚拟环境。
- 不推送远端。

验证：
- 使用 rg --files 检查目标文件位置；
- 检查 Markdown 相对链接指向的文件是否存在；
- 运行 git diff --check；
- 运行 git status --short。

如果验证通过，只暂存本步骤明确修改的文档，创建本地提交：
docs: 确立V1.1A开发基线

如果工作区存在无法区分的用户修改，不要提交，保留修改并说明原因。

最后报告：修改/移动文件、验证结果、提交哈希（若创建）、仍保留的未跟踪文件。然后停止，不要进行 Django 初始化。
```

验收条件：

- PRD 和架构文档进入正确的 `docs` 目录。
- `AGENTS.md` 已建立，后续 Codex 能自动读取项目规范。
- 根目录模型代码没有丢失。
- 没有开始生成 Django 业务代码。

## 第 3 步：创建最小可运行的 Django 单体骨架

```text
继续 OpsAI-IT 项目的第 3 步：创建最小可运行的 Django 单体项目骨架。本步骤只做工程骨架，不开发知识库业务接口。

开始前必须：
1. 确认位于唯一正式仓库根目录，并读取 AGENTS.md、README.md、docs/02-PRD 下的 V1.1A PRD、docs/04-Architecture 下的两份架构文档。
2. 运行 git status --short；保护现有修改。
3. 检查本机 Python 版本。目标为 Python 3.13；若没有 3.13，不要全局安装或偷偷改版本，先报告可用版本和影响并停止。

需要完成：
1. 按 Django项目模块目录结构.md 在仓库根目录建立：
   - manage.py
   - config/settings/base.py、development.py、test.py、production.py
   - config/urls.py、asgi.py、wsgi.py
   - apps/core、accounts、knowledge、search、workflow、dingtalk、service_desk、audit
   - templates、static/css、static/js、static/images、private_media、tests
2. 每个 App 只创建标准的 apps.py、__init__.py 和必要空模块；不要提前实现业务。
3. 在 accounts 中建立最小的自定义 User 占位模型，继承 AbstractUser，使 AUTH_USER_MODEL = "accounts.User" 从第一次迁移前就确定。本步骤不要生成迁移。
4. core 只实现 GET /health/live，返回简单 JSON 和 HTTP 200；不要检查数据库或外部系统。
5. 创建 pyproject.toml，依赖只包含当前启动必需项：Django 5.2 LTS、PostgreSQL 驱动和最小环境变量支持；开发工具可加入 pytest、pytest-django、ruff，但不要引入 DRF、Celery、Redis、Elasticsearch。
6. 创建项目目录内的 .venv 并安装项目依赖；不得全局安装。
7. 配置模板、静态文件、时区、中文语言、日志基本格式和分环境设置。密钥全部读取环境变量。
8. 创建 .env.example，只写变量名和安全示例；真实 .env 必须被 .gitignore 排除。
9. 更新 README.md，写清 Windows 下创建/激活 .venv、安装依赖、运行 check 和启动开发服务器的命令。

边界：
- 不迁移数据库；
- 不实现 Department、UserGroup、Article 等正式模型；
- 不复制根目录 models.py；
- 不创建首页、搜索、审核、钉钉或 IT 服务 API；
- 不添加 Docker、Caddy、ClamAV；
- 不推送远端。

必须验证：
- 使用 .venv 中的 Python 运行 python manage.py check；
- 运行 python manage.py check --settings=config.settings.test；
- 对当前代码运行 ruff check（若已配置）；
- 请求 /health/live 的最小测试通过；
- git diff --check 通过。

若验证通过，只提交本步骤文件，创建本地提交：
chore: 初始化Django单体项目骨架

最后报告：新增目录树、依赖版本、验证命令及结果、提交哈希、下一步需要完善的 accounts 模型。报告后停止。
```

验收条件：

- `python manage.py check` 通过。
- `/health/live` 测试通过。
- `AUTH_USER_MODEL` 在首次迁移前已确定。
- 8 个 App 只有骨架，没有越界实现业务。

## 第 4 步：完成 accounts 基础数据模型和首次迁移

```text
继续 OpsAI-IT 项目的第 4 步：完成 accounts App 的基础数据模型。本步骤只实现 knowledge 模型所依赖的账号与组织数据，不开发登录接口和钉钉同步。

开始前读取 AGENTS.md、V1.1A PRD 第 7～9 章、Django项目模块目录结构.md，以及根目录待集成 models.py 中声明的外部依赖。检查 git status，确保第 3 步已完成。

需要完成：
1. 在 apps/accounts/models.py 中实现并写清中文 verbose_name 和必要数据库注释：
   - User：继承 AbstractUser，预留钉钉用户唯一标识、员工编号、姓名、账号状态等 V1.1A 必需字段；
   - Department：支持钉钉部门标识、名称、父部门、启用状态；
   - UserDepartment：支持一个用户属于多个部门并标识主部门；
   - UserGroup：仅表示内容受众用户组，不等同于系统操作角色；
   - UserGroupMembership：用户与内容用户组关系。
2. 外键 on_delete、related_name、唯一约束、检查约束和常用索引必须明确；不能用字符串或逗号字段代替多对多关系。
3. 系统操作角色本步骤优先复用 Django Group/Permission；若 PRD 明确要求额外字段，只做最小扩展并说明，不要自建复杂权限平台。
4. 注册最小可用 Django Admin，便于查看用户、部门和内容用户组。
5. 生成 accounts 的首次迁移；确保自定义 User 出现在 0001_initial 中。
6. 为模型关系、唯一约束、主部门规则和删除保护编写测试。

边界：
- 不实现钉钉 API、免登、通讯录同步；
- 不实现知识模型；
- 不开发 REST API 或业务页面；
- 不修改根目录 models.py；
- 不推送远端。

必须验证：
- python manage.py makemigrations --check --dry-run
- python manage.py migrate --settings=config.settings.test
- python manage.py check
- accounts 相关测试
- ruff check
- git diff --check

验证通过后创建本地提交：
feat(accounts): 建立用户部门与内容用户组模型

最后逐项报告模型、约束、迁移、测试结果和提交哈希，然后停止。
```

验收条件：

- 首次迁移中已经包含自定义 `User`。
- 内容用户组与系统角色没有混用。
- `Department`、`UserGroup` 可以被知识模型外键引用。
- 模型及约束测试通过。

## 第 5 步：建立 PostgreSQL 本地开发环境

```text
继续 OpsAI-IT 项目的第 5 步：建立 PostgreSQL 本地开发环境。本步骤只完成开发基础设施，不加入生产部署和其他服务。

开始前读取 AGENTS.md、架构文档和现有 settings；检查 git status。保持 Python 3.13 + Django 5.2 LTS + PostgreSQL 技术路线。

需要完成：
1. 创建适合本地开发的 Dockerfile 和 compose.yaml（可放 deploy/，但 README 命令必须明确）。
2. Compose 本步骤只包含最小的 web 与 db 服务：
   - PostgreSQL；
   - Django 开发服务。
3. 为数据库配置健康检查、命名卷和非默认示例账号；真实密码只从未跟踪的 .env 读取。
4. Django development settings 连接 PostgreSQL；test settings 保持独立、可重复运行。
5. 更新 .env.example、.gitignore 和 README，写清 Windows + Docker Desktop 的启动、停止、迁移、创建管理员命令。
6. 增加 GET /health/ready：检查数据库连接和私有附件目录可写性，不访问钉钉。
7. 不提交 .env、数据库数据、虚拟环境和日志。

边界：
- 不加入 Caddy、ClamAV、Redis、Celery、Elasticsearch；
- 不部署到公网或公司服务器；
- 不实现知识业务；
- 不推送远端。

必须验证：
- docker compose config
- 若 Docker 可用：启动 db，等待健康后执行 Django migrate 和 check
- /health/live 返回 200
- /health/ready 在依赖正常时返回 200；数据库不可用时返回明确但不泄密的非 200 状态
- 运行测试和 git diff --check

如果 Docker 在当前环境不可用，不要伪造运行结果；完成静态配置检查后明确列出需要我在本机执行的命令。

验证通过后创建本地提交：
chore: 建立PostgreSQL本地开发环境

最后报告服务、端口、变量、健康检查、验证结果和提交哈希，然后停止。
```

验收条件：

- Docker 配置可解析。
- 数据库口令没有进入 Git。
- PostgreSQL 上能完成迁移，或明确给出因当前环境缺少 Docker 而未执行的本机验证命令。
- 还没有引入生产环境复杂组件。

## 第 6 步：将已生成的 knowledge 模型正式接入项目

```text
继续 OpsAI-IT 项目的第 6 步：接入 knowledge 核心数据模型。本步骤只处理模型、迁移、Admin 和模型测试，不开发页面、服务流程或 API。

开始前：
1. 读取 AGENTS.md、V1.1A PRD 第 8～9 章、Django项目模块目录结构.md、系统架构与API接口清单.md。
2. 完整读取仓库根目录 models.py，并把它视为已验证的 knowledge 模型候选代码，不能凭空重写。
3. 检查 accounts.User、Department、UserGroup 已存在；检查 git status 并保护用户修改。

需要完成：
1. 将根目录 models.py 的知识模型接入 apps/knowledge/models.py，至少包含：
   - KnowledgeSpace
   - Category
   - Article
   - ArticleVersion
   - ArticleAudience
   - ReviewRecord
2. 根据实际 app 路径修正引用，但保留已设计的字段、外键、related_name、on_delete、索引、条件唯一约束、检查约束、中文字段说明和 db_comment。
3. 将候选代码逐项对照 PRD 第 8～9 章；若发现冲突，优先遵循 V1.1A 并在报告中列出差异，不要静默删字段。
4. 确认 Article.current_published_version 和 latest_working_version 的循环外键迁移顺序可正确生成。
5. 在 Django Admin 注册这些模型，只提供基础查询和筛选，不实现发布按钮。
6. 生成 knowledge 迁移。
7. 编写模型级测试，至少覆盖：
   - KB-000001 编号格式和唯一性；
   - 分类与知识空间关系；
   - 一篇文章仅一个工作版本和一个已发布版本；
   - 受众目标互斥和允许/拒绝规则；
   - 作者不可审核自己的内容；
   - PROTECT 删除策略；
   - 关键索引和约束存在。
8. 确认接入成功后，根目录不再保留重复的 models.py；删除前必须先确认完整内容已进入 apps/knowledge/models.py 并受 Git 跟踪。

边界：
- 不实现知识编号生成服务；
- 不实现发布、驳回、下架事务；
- 不实现搜索、受众查询、API 或页面；
- 不实现钉钉；
- 不推送远端。

必须验证：
- python manage.py check
- python manage.py makemigrations --check --dry-run
- 在 PostgreSQL 开发库或独立测试库执行迁移
- knowledge 与 accounts 全部测试
- ruff check
- git diff --check

验证通过后创建本地提交：
feat(knowledge): 接入知识文章版本受众与审核模型

最后报告：模型和关系清单、生成迁移、测试数量与结果、PRD 差异、根目录 models.py 的处理结果、提交哈希。报告后停止。
```

验收条件：

- 核心知识模型完成迁移。
- 关键约束在数据库和测试中均有体现。
- 根目录候选代码没有被误删或遗漏。
- 没有提前实现业务 API。

---

# 第二阶段以后：完整系统开发顺序

第 1～6 步完成后，不要直接要求 Codex“把剩余系统全部完成”。建议继续按下面顺序，一次一个步骤生成和执行详细指令。

| 步骤 | 单一目标 | 主要验收点 |
| --- | --- | --- |
| 7 | 建立本地模拟登录和系统操作角色 | 开发环境可切换员工/编辑/审核/管理员；生产环境强制关闭模拟登录 |
| 8 | 实现内容受众权限选择器 | 拒绝优先、部门/用户组/用户/仅 IT 规则测试完整，无权限不泄露文章存在性 |
| 9 | 配置 Django Admin 和最小演示数据 | 可创建空间、分类、用户、受众和测试文章；脚本可重复执行 |
| 10 | 开发首页、分类页和知识详情页 | Django Templates + Bootstrap + HTMX；PC/手机响应式；只展示可见已发布内容 |
| 11 | 开发 P0 搜索 | 标题、标签、别名、摘要、正文排序；权限先过滤；记录搜索和点击 |
| 12 | 开发文章创建、草稿和版本保存 | 创建、手动保存、自动保存、预览、版本链；不含审批决定 |
| 13 | 开发提交审核、批准、驳回和发布事务 | 作者不可自审；事务原子性；旧版本替代；幂等测试 |
| 14 | 开发反馈、下架和复审 | 反馈队列、紧急下架、到期复审；全程保留审计记录 |
| 15 | 开发私有附件和病毒扫描 | 隔离上传、鉴权下载、扫描通过才能发布；禁止公开媒体直链 |
| 16 | 开发 Outbox、通知重试和审计 | 事务内写 Outbox；Worker 发送；失败重试幂等；敏感操作可查询 |
| 17 | 接入钉钉免登、JSAPI 和通讯录同步 | 先用测试企业；AppSecret 仅在服务端；回调验签、防重放 |
| 18 | 接入统一 IT 服务入口 | 先实现 P0 安全跳转与降级；目标系统支持时再启用 P1 context_token |
| 19 | 完成 Docker 生产配置 | Gunicorn、Caddy、PostgreSQL、备份、健康检查、日志和安全响应头 |
| 20 | V1.1A 验收与试点发布 | P0 接口、权限、搜索词、30～50 篇知识、备份恢复和回滚演练通过 |

## 三、每一步完成后的通用复核指令

如果 Codex 表示某一步已经完成，可以再单独发送下面这条复核指令。复核通过后再进入下一步。

```text
请只复核刚刚完成的当前步骤，不新增功能。

1. 对照当前步骤原始任务逐条列出“已完成、未完成、偏离范围”。
2. 查看 git diff、git status 和本步骤提交内容，确认没有夹带无关文件、密钥、.env、虚拟环境、数据库文件或日志。
3. 重新运行该步骤要求的 check、迁移检查、测试、ruff 和 git diff --check。
4. 检查是否提前实现了下一阶段功能；如有，说明并提出最小回退方案，但不要擅自执行破坏性回退。
5. 输出：验收结论、测试证据、遗留问题、风险、是否可以进入下一步。

本次只复核和报告，不修改代码、不提交、不推送。完成后停止。
```

## 四、何时推送 GitHub 和 Gitee

建议每完成一个稳定里程碑再双端推送，不必每一步都推：

- 里程碑 A：第 1～3 步完成，Django 骨架可运行；
- 里程碑 B：第 4～6 步完成，accounts 与 knowledge 迁移和测试通过；
- 里程碑 C：第 7～13 步完成，核心知识闭环可演示；
- 里程碑 D：第 14～20 步完成，V1.1A 可以试点。

推送前先复核远端配置。已配置 `origin` 同时推送 GitHub 与 Gitee 时，可在确认提交无误后由用户明确授权 Codex 执行：

```text
请先只读检查 git status、当前分支、最近提交和 git remote -v。确认工作区无未提交业务修改，且 origin 的 push URL 同时包含 GitHub 与 Gitee 后，执行 git push origin main。不得更改远端、不得强制推送。完成后分别报告两个远端的推送结果。
```
