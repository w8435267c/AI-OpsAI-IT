# OpsAI Current Task

> 当前没有获授权的后继业务开发任务。`KB-MULTI-FORMAT-IMPORT-01` 已于 2026-11-28 完成证据与状态收口；不得因此自动启动 Task 13、Task 14 或其他任务。

## 1. 已完成任务（历史收口）

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `KB-MULTI-FORMAT-IMPORT-01` |
| 任务名称 | 多格式知识文档导入与统一富文本知识内容 V1.1 |
| 任务状态 | `DONE` |
| 工作树 | `D:\Desktop\OpsAI\AI-OpsAI-IT-multi-import` |
| 分支 | `feature/kb-multi-format-import-01` |
| 起始 HEAD | `8b982ef994d19fc37806ab49c4f5c17fe33658da` |
| 上游能力 | 复用已提交的版本媒体、私有存储、ClamAV 失败关闭、DOCX 导入、草稿编辑与审核发布；不得复制审核流程。 |
| 可修改文件 | `apps/knowledge/` 中结构化正文模型、迁移、内容校验/渲染、导入服务、媒体关联、表单、视图、路由、模板、项目自有 JS/CSS 和测试；必要 `apps/audit/` 审计接线；本地 vendor 编辑器资源及其许可证记录；`pyproject.toml` 及实际存在且必须同步的锁定文件；必要隔离验收配置；`tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml`。 |

### 1.0 最终收口结论（2026-11-28）

- 最终验收报告：`docs/KB-MULTI-FORMAT-IMPORT-01_最终验收报告.md`。该报告记录负责人 Firefox 四格式人工验收、KB-000009 有权阅读和无权文章/媒体拒绝、P1 后继草稿图片关联修复及回滚验证。
- 实现提交：`4589dbd71885b27309e9be9ec51000d5981135a2`，已是正式分支 `fusion/wagtail-poc` 当前 HEAD `4436547d25893a079e7192f73d5ffbe06102dd40` 的祖先；GitHub 与 Gitee 的该正式分支均已核验为当前 HEAD。
- 历史测试证据（非本轮重跑）：`pytest apps -q` 为 `965 passed, 23 skipped, 737 subtests passed`；P1 媒体专项为 `65 passed, 89 subtests passed`；Django check、迁移一致性、Ruff、JS 检查和 `git diff --check` 通过。
- 遗留限制：Windows 未信任 18027 内部根 CA；镜像标签不能单独证明运行容器与当前正式分支逐字节一致；根目录 `pytest -q` 会误收集历史 Wagtail PoC 并出现 16 个环境/导入错误，不能称为全仓绿色。
- 后续状态：等待项目负责人指定并授权唯一下一项任务；不得自动将 Task 13 或 Task 14 设为进行中。

### 1.1 范围与验收

- 第一批只支持 `.docx`、`.pdf`、`.txt`、`.md`；第二批 `.doc`、`.odt`、`.rtf` 仅保留明确拒绝提示，不实现解析。
- 各格式使用独立受限解析器，但共用私有临时区、真实格式验证、ClamAV 扫描、标题/正文归一化、创建新草稿、既有编辑和审核发布路径；原始导入文件不自动公开或作为附件。
- DOCX 保留标题、段落、列表、PNG/JPEG 内嵌图片及正文位置；PDF 仅处理有可靠文本层且未加密的文档，不承诺图片或复杂表格；TXT 支持 UTF-8、UTF-8 BOM 和受控常见中文编码；Markdown 只解析标题、段落、列表和代码块，禁止原始 HTML、脚本和外部资源。
- 导入必须限制大小、真实格式、PDF 页数/解析资源、DOCX 解包规模、图片数量和解析耗时；扫描或解析失败、格式伪造、越权、重复提交或不安全内容不得留下可见草稿、媒体或私有残留。
- 创建页改为“导入知识文档”，显示支持格式、限制、处理状态、提取预览和不兼容内容提示；保留既有空间、分类、文章类型、适用范围、受众及生效时间字段。
- 使用全新隔离测试库与私有媒体卷验证各合成样本、失败关闭、编辑/审核/发布/员工读取和 DOCX 图片能力回归；运行专项、应用回归、Django check、迁移一致性、依赖与静态检查。全部必需项通过后才可本地提交。

### 1.1A 范围扩展：统一富文本知识内容（负责人授权，2026-11-22）

- 保留同一 `Article` / `ArticleVersion`、私有媒体、扫描、审核发布、受众过滤与审计流程；不得建立第二套文章、版本或审核状态机。
- 将 `ArticleVersion.body` 演进为服务端验证的版本化结构化 JSON 权威正文；`body_plaintext` 只能由其派生，旧 `opsai.plaintext/1` 正文继续兼容读取与编辑升级。
- 第一版节点范围为标题、段落、文字与安全标记、列表、代码块、引用、表格、私有图片/图注、提示框和安全超链接；禁止任意 HTML、脚本、外部图片、临时链接或私有存储路径进入正文。
- 四种导入均归一为标题、结构化正文、源格式、受控原始源文件、导入媒体、转换警告和派生纯文本；原文件只向具备既有管理权限的人员开放核对，不自动成为员工下载附件。
- DOCX 增强为按段落与表格顺序解析，保留受支持标题、强调、安全颜色、列表、表格、内嵌 PNG/JPEG、图注和可识别提示；无法可靠转换的内容必须产生中文警告，不能返回无说明的 500。
- 编辑与预览使用本地打包、固定版本、MIT 许可的 Tiptap 开源核心和最小扩展；不使用 CDN、云端编辑服务或大型前端应用。管理预览和员工正式阅读复用同一受控 JSON 解释/渲染规则。
- 本轮阶段依次为 F1 结构化模型与旧数据兼容、F2 DOCX 保真转换、F3 编辑/预览、F4 四格式统一接入、F5 员工阅读/权限、F6 隔离浏览器联合验收。浏览器未完成前保持 `BLOCKED`，不得标记 DONE/PASS。

### 1.1B 范围扩展：正文编辑区统一与剪贴板图片（负责人授权，2026-11-23）

- `opsai.richtext/1` 草稿只以 Tiptap 为正文编辑权威入口；旧 `body_text` 仅展示由结构化正文派生的折叠只读摘要，且旧纯文本版本仍保留原 textarea 编辑路径。
- 浏览器仅可将剪贴板实际提供的 PNG/JPEG `File`/`Blob` 交给既有当前版本媒体上传接口；服务端格式校验、私有存储、ClamAV、`ArticleVersionMedia` 归属校验和 CAS 保存不变。不得写入 data URL、外部 URL、`file://`、原始 HTML 或绕过扫描。
- 异步扫描期间保持粘贴时的文档位置映射；成功后插入内部媒体 ID，失败/位置失效时不插入正文并给出中文提示。普通文字和表格粘贴不应被拦截，浏览器人工验收仍为必需项。

### 1.2 开工核验（2026-11-22）

- 主线 `fusion/wagtail-poc` 位于 `8b982ef994d19fc37806ab49c4f5c17fe33658da`，存在 10 项未提交的试点部署/任务登记改动；未复制、修改、暂存或重置。
- 本工作树和功能分支从该已提交 HEAD 新建，开工时干净；已确认媒体与 DOCX 导入能力在历史中可复用。
- 当前尚未选择 PDF 解析依赖；选择前必须核对 Python 3.13 兼容性、维护状态、许可、实际安全用途和 wheel/隔离构建可用性。

### 1.3 历史阶段验证记录（2026-11-22 起；以 1.0 最终收口结论为准）

- 独立 Python 3.13 `.venv` 已离线校验并安装 `pypdf-7.1.1`；官方给定 SHA-256 与本地 wheel 一致。专项 DOCX/PDF/TXT/Markdown 解析和导入回归为 `24 passed`；正式 `apps/` 回归在仅进程内合成 PostgreSQL 占位变量下为 `924 passed, 23 skipped, 723 subtests passed`。仓库根 `pytest` 仍因既有未安装 Wagtail 实验目录在收集阶段失败，不能计为本任务失败或全量通过。
- 已新建并仅使用 `opsai-multi-import-acceptance-01-*` 的 PostgreSQL、ClamAV、私有媒体卷、网络和 Web 镜像；未触碰 18025、18443、既有容器或历史卷。空库实际应用 `knowledge.0001` 至 `0009`、`audit.0001` 至 `0002`；隔离镜像已由经核验的 Linux `cp313`/x86_64 Pillow 12.3.0 wheel 重建，运行容器实测 `Pillow 12.3.0`、`gunicorn 27.0.0`、`pypdf 7.1.1`、`pip check` 和 Django check 通过。Pillow 12.3.0 Linux wheel 不适用于 Windows `.venv`，Windows 环境保持 11.3.0，未混用 ABI。
- 真实 ClamAV 对合成干净内容返回 `clean`，强制不可用主机返回 `failed`。经真实扫描的合成 DOCX、PDF、TXT、Markdown 分别创建 `KB-000001` 至 `KB-000004` 草稿，均未自动发布；扫描器不可用时导入返回 `DOCUMENT_IMPORT_SCAN_FAILED` 且文章数量不变。
- 真实 ClamAV 对容器内合成干净文件返回 `clean`；Pillow 12.3.0 实测可解码 PNG/JPEG。已在隔离数据库准备编辑员、审核员、授权员工、无权员工、审核空间范围与受众组；所有账号均启用且无可用密码，密码仅能由负责人通过 Django `changepassword` 交互式设置。Caddy 导出的公开根证书 SHA-256 已与当前 Caddy 容器内 `root.crt` 一致，未导出私钥、未修改 Windows 根证书库。
- 浏览器自动化未通过：专用 Caddy 已提供 `https://localhost:18027`，其独立公开根证书已由显式 CA 上下文验证，且未修改 Windows 根证书库；受控浏览器仍无法向临时 Profile 导入该 CA，因此尚未完成真实登录、导入、发布、受众拒绝及 390×844 验收。不得以 HTTP/单元测试替代浏览器 PASS，任务保持 `BLOCKED / manual browser E2E pending`，不得提交或标记 DONE。
- 2026-11-23：富文本草稿编辑页将派生 `body_text` 改为折叠只读摘要，Tiptap 为唯一正文编辑入口。剪贴板 PNG/JPEG 仅复用既有当前版本私有媒体上传与 ClamAV 路径，扫描成功后以内部媒体关联 ID 插入并映射原光标位置；不保存 data URL 或外部图片。自动化为编辑/媒体专项 `71 passed, 192 subtests passed`，完整 `apps/` 回归 `945 passed, 23 skipped, 733 subtests passed`，Ruff、Django check、迁移一致性、JS 语法、富文本构建和 `git diff --check` 均通过。隔离 Web 已更新为 `sha256:91e46f5838d11db72962d3aeafa4df26dc2759945fa6654701ee7e00772f8693`；真实 Firefox 粘贴、保存重开及移动视口尚未人工验收，任务仍为 `BLOCKED`。
- 2026-11-23：Firefox 证据显示粘贴后直接出现“受控图片不可读取”。隔离日志中的对应上传请求均为 `200`，数据库中的新增当前草稿媒体关联均为 `clean`，故排除上传/ClamAV 失败。根因是 Tiptap `configure()` 深拷贝了初始媒体 URL 映射，异步注册的新 URL 未进入图片节点渲染器；有效图片粘贴又错误返回 `false`，未阻止默认 HTML 粘贴。现改为由图片节点闭包读取同一可变 URL 映射，并对真实 PNG/JPEG 粘贴 `preventDefault()` 后返回 `true`。专项 `72 passed, 192 subtests passed`，完整 `apps/` 回归 `946 passed, 23 skipped, 733 subtests passed`；隔离 Web 已更新为 `sha256:f7cdfd721e71c7b563c328a6f877ef67847e5afb1778ec0caf8b3173133d328d`。仍需 Firefox 保存、刷新和位置复验，状态保持 `BLOCKED`。
- 2026-11-23：`KB-000009` v1（`940f5f8e-4551-46bc-b169-301feb2aa396`）实际为 `in_review` 的 `opsai.richtext/1` 快照，含 4 个图片节点、4 个表格、9 个 clean 当前版本媒体关联，且无工作草稿/正式版本。历史详情此前只投影 `body_plaintext`，故丢失图文展示；现以既有安全渲染器和精确历史版本媒体路由渲染，不修改快照、状态或媒体关联。历史专项 `28 passed, 26 subtests passed`，完整 `apps/` 回归 `947 passed, 23 skipped, 733 subtests passed`；隔离 Web 已更新为 `sha256:a2711b995f978675fa928e2d83c3d05b0006d542bb12f1bc0c6bd5b7fc820946`。人工浏览器复验前保持 `BLOCKED`。

- 2026-11-23：`KB-000009` v1 的 4 个表格 JSON、`table/tr/th/td` HTML 与历史数据均保持正确（12 个表头单元格、35 个普通单元格，无合并跨度）；阅读态表格此前只有编辑器作用域 CSS，故缺少边框和表头视觉。现统一为四个阅读页面的 `richtext-body` 样式：清晰蓝白边框、内边距、中文长文本换行，以及仅表格容器横向滚动。专项 `30 passed, 26 subtests passed`，完整 `apps/` 回归 `949 passed, 23 skipped, 733 subtests passed`；Django check、迁移一致性、Ruff、JS 语法、富文本构建、静态 CSS HTTP 响应和 `git diff --check` 均通过。隔离 Web 已更新为 `sha256:eb82c373f16d09a5b853af1f35f04243212caba276664be4951c5d9661321b0f`；仍待 Firefox 人工复验，任务保持 `BLOCKED`。

- 2026-11-23：经负责人授权，仅在 `opsai-multi-import-acceptance-01` 将 `KB-000009` 的测试受众从 `all_employees` 收紧为 `restricted`，新增唯一 `user_group / allow / multi-import-authorized-readers` 规则；未修改账号、正文、版本、图片、表格、发布状态或原始导入文件。正式 v1、文章状态、两条版本记录和 9 条有效媒体关联的修改前后核验一致。真实隔离服务验证：`multi-import-reader` 搜索、详情和图片均为允许/HTTP 200；`multi-import-denied` 搜索不命中、详情和图片均为 HTTP 404，管理和审核原始文件入口也均为 HTTP 404。审核员原始文件下载为 HTTP 200 并新增 1 条下载审计。相关回归 `157 passed, 68 subtests passed`，Django check 与 `git diff --check` 通过；仍待 Firefox 人工权限复验，任务保持 `BLOCKED`。

## 2. 已替换的前一当前任务登记（历史保留）

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `KB-DOCX-IMPORT-DRAFT-01` |
| 任务名称 | 单篇 Word 导入知识草稿 |
| 任务状态 | `DONE / LOCAL ISOLATED ACCEPTANCE PASS` |
| 工作树 | `D:\Desktop\OpsAI\AI-OpsAI-IT-kb-docx-import` |
| 分支 | `feature/kb-docx-import-draft-01` |
| 起始 HEAD | `63c3205849a7ce82a49735b3a1170bc65f266c59` |
| 上游媒体能力 | 复用已验收的版本媒体关联、私有存储、实际格式校验、ClamAV 扫描、发布门禁、受众鉴权下载及审计；不修改其已验收工作树。 |
| 原工作区依赖 | 无。原工作区 20 项未提交改动只读核验，保持原样。 |

### 1.1 精确修改范围

- `apps/knowledge/`：仅限单篇 `.docx` 解析、导入事务服务、创建页面入口、必要的管理路由/视图、既有草稿与版本媒体复用接线及测试。
- `templates/knowledge/manage/create.html`、必要的项目自有 JS/CSS：导入入口、可理解的失败和不支持内容提示；不新增编辑器。
- `pyproject.toml`：仅在现有依赖不能安全解析 `.docx` 时新增固定用途依赖；新增前后记录实际用途。
- `deploy/`：仅在现有隔离媒体验收配置确实无法复用时，新增本任务专用且隔离的配置；不得修改正式 Compose、Caddy 或既有数据卷。
- `tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml`：任务登记和真实验收结果。

### 1.2 验收与安全边界

- 每次导入只创建一篇新的未发布草稿；不得覆盖既有文章、自动提交审核或自动发布。分类、受众和其他必填项继续走现有创建表单、权限与服务校验。
- 仅支持 `.docx` 的标题、段落、有序/无序列表和内嵌 PNG/JPEG；按原始正文顺序保存，图片绑定导入草稿版本。原始 Word 不作为文章附件。
- 表格、浮动图及不能可靠转换的内容必须明确提示；核心解析失败、扫描失败/不可用、越权或重复提交均失败关闭，不留可见半成品草稿、未引用媒体或临时文件。
- 原始 `.docx` 与提取图片均走已有格式校验、私有区和扫描；限制上传大小、解包总量、条目数和图片数，拒绝宏、嵌入对象和外部资源。不得执行文档内容，也不得把原始 XML/HTML 直接插入正文。
- 隔离验收须覆盖合成 Word 的导入、编辑保存重开、现有审核发布、授权阅读/看图、无权图片直链拒绝，及桌面与 `390×844` 浏览器视口。全部通过后才可本地提交；不 Push、不 Merge、不部署。

### 1.3 实际收口证据（2026-11-19）

- 未新增依赖或迁移；`.docx` 使用标准库受限解包与 XML 白名单读取。原始文档仅在私有临时区完成格式校验与真实 ClamAV 扫描后删除，提取图片同样扫描后才作为当前草稿版本媒体保存；原始 Word 不附加到文章。
- 自动化新增 `apps/knowledge/tests/test_docx_import.py`：合成标题/步骤/PNG 导入、草稿版本关联、列表、表格/外部资源拒绝、扫描失败无残留、权限与重复提交；专项及媒体/创建回归 `34 passed, 25 subtests passed`。正式应用范围 `902 passed, 23 skipped, 723 subtests passed`；23 项为 SQLite 测试设置下仅 PostgreSQL 的既有并发专项。
- `DJANGO_SETTINGS_MODULE=config.settings.test python manage.py check`、`makemigrations --check --dry-run`、任务范围 Ruff lint/format 与 `git diff --check` 通过。仓库根目录裸 pytest 仍会因未安装的 Wagtail 隔离 PoC 收集失败，根目录全量 Ruff format 仍命中一处既有未修改格式差异，均未表述为通过。
- 复用未重建的 `opsai-kb-media-acceptance` 隔离 PostgreSQL/ClamAV（15433、3311 均仅 127.0.0.1）；真实 ClamAV 对合成 PNG 返回 `clean`。浏览器以合成 Word 导入 `KB-000003`，编辑保存重开为 v2，走现有审核发布；员工端顺序为第一步、第二步（编辑后）、图片、第三步。390×844 下 `scrollWidth=375`、`clientWidth=375`，无横向溢出；退出登录后同一图片直链返回“需要有效员工身份”。

## 2. 已替换的前一当前任务登记（历史保留）

## 1. 前一任务

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `KB-ARTICLE-MEDIA-MVP-01` |
| 任务名称 | 知识正文插图与 Word 私有附件 MVP |
| 任务状态 | `DONE / LOCAL ISOLATED ACCEPTANCE PASS` |
| 工作树 | `D:\Desktop\OpsAI\AI-OpsAI-IT-kb-article-media` |
| 分支 | `feature/kb-article-media-mvp-01` |
| 起始 HEAD | `87f1e95d69122de2b39aacc95dfa3b174393b532` |
| 集成目标分支 | `fusion/wagtail-poc`（仅记录；本轮不合并、不推送） |
| 原工作区依赖 | 无。原工作区 20 项未提交改动只读核验后确认不含媒体、扫描、私有下载或版本媒体关联实现。 |

### 1.1 精确修改范围

- `apps/knowledge/models.py`、`apps/knowledge/migrations/`：版本媒体元数据及迁移；媒体只关联 `ArticleVersion`，不硬删除历史记录。
- `apps/knowledge/media_services.py`、`apps/knowledge/media_scanning.py`、`apps/knowledge/media_readers.py`、`apps/knowledge/media_views.py`、`apps/knowledge/media_forms.py`：私有存储、真实 ClamAV 扫描适配、编辑和下载服务、鉴权读取。
- `apps/knowledge/manage_views.py`、`apps/knowledge/manage_urls.py`、`apps/knowledge/views.py`、`apps/knowledge/urls.py`、`apps/knowledge/readers.py`：编辑入口、发布版本展示和受众鉴权路由接线。
- `apps/workflow/services.py`：发布事务内的扫描通过校验；不得复制或替换既有审核状态机。
- `apps/audit/models.py`、`apps/audit/migrations/`：仅增加媒体上传/下载审计事件类型；审计仍为追加式。
- `templates/knowledge/manage/edit.html`、`templates/knowledge/article_detail.html`、`static/css/opsai.css`：编辑上传入口、员工展示与移动端样式。
- `pyproject.toml`、`config/settings/base.py`、`config/settings/test.py`：新增 Pillow 用于真实 PNG/JPEG 解码验证，以及扫描连接和文件大小配置；正式默认失败关闭，测试替身不得成为正式放行条件。
- `deploy/compose.media-acceptance.yaml`、`deploy/media-acceptance.env.example`：新建独立 PostgreSQL + ClamAV 隔离验收环境；不修改现有 Compose、Caddy 或数据卷。
- `apps/knowledge/tests/test_media_*.py`、`apps/workflow/tests/test_media_publish_gate.py`、`apps/audit/tests/test_media_audit.py`：功能、安全、发布和回归测试。
- `tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml`：本任务登记与最终真实验证结果。

### 1.2 验收与边界

- 仅接受经真实格式验证的 PNG、JPEG、`.docx`，限制大小；拒绝 SVG、宏文档、伪造 MIME 和超限文件。
- 上传先写私有区并记录扫描状态；待扫描、失败、超时、不可用或未通过均禁止发布和下载。ClamAV 使用 TCP `clamd` 协议，正式默认没有扫描器即失败关闭。
- 图片和 Word 均走鉴权路由；员工只可读取其可见文章的当前已发布版本媒体。草稿、历史版本、下架、跨文章/版本和无权直链均返回不泄露存在性的 404；响应禁止共享缓存。
- 发布校验在服务端事务路径执行。删除草稿媒体只解除版本引用，不清理私有文件；历史媒体留存与后续受控清理策略记录在模型/服务注释中。
- 使用新建隔离 PostgreSQL、独立媒体目录和独立 ClamAV 完成真实扫描、迁移、浏览器桌面与 `390×844` 验收；若任一项未完成，不标记整体 PASS。
- 允许在全部必需验收通过后只对本任务文件创建一个本地提交；不合并、不推送、不切换或修改原工作区。

### 1.3 实际收口证据（2026-11-19）

- 隔离 `opsai-kb-media-acceptance` 的 PostgreSQL 已实际应用 knowledge 0009 与 audit 0002；现有容器、卷和原工作区均未重建或修改。
- 独立 INSTREAM 诊断收到 `stream: OK\0` 与 `stream: Eicar-Test-Signature FOUND\0`；适配器已修复 TCP 分段回包读取，完整明确的 OK 才放行，FOUND 映射为 infected。EICAR 与合成样本未写入仓库。
- 自动化：正式应用范围 `890 passed, 23 skipped, 6 deselected, 723 subtests passed`；媒体专项 `50 passed, 102 subtests passed`；Django check、迁移一致性、Ruff（任务范围）、JS 语法及 `git diff --check` 通过。根目录全量 pytest 仍会因历史 `experiments/wagtail_*` 未安装的 PoC 依赖而收集失败，未将其表述为通过。
- 浏览器：隔离 PostgreSQL 合成数据完成编辑上传 PNG 与 .docx、保存重开、审核发布、授权员工插图定位与 Word 下载（下载审计 1 条）、拒绝优先受众直链 404；390×844 视口 scrollWidth 375，小于视口 390，无横向溢出。

## 2. 已替换的前一当前任务登记（历史保留）

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `PILOT-KNOWLEDGE-LIST-STATUS-01` |
| 任务名称 | OpsAI 知识管理列表待审标题与状态修复 |
| 任务状态 | `DONE / PASS（未提交改动，待负责人验收）` |
| 任务性质 | `MANAGE LIST READ MODEL ONLY` |
| 登记基线 | `e3531e522f0b3cef706418b91f0a21e3b016210f` |
| 目标分支 | `fusion/wagtail-poc` |
| 前置依赖 | `PILOT-HOME-ROLE-NAV-01` 已由提交 `e3531e522f0b3cef706418b91f0a21e3b016210f` 收口为 `DONE / PASS`。 |
| 当前授权 | 仅允许定位并修复知识管理列表读取、必要模板和测试；可复用 18016 临时隔离环境验证；不修改 KB-000001、KB-000002 或其他既有文章数据，不新增迁移、不修改审核流程、权限、钉钉或部署。 |

## 2. 本轮实施范围与验收

- 先以合成数据复现首次送审、已发布版本后存在待审新版本、普通草稿和无有效标题边界，核对管理列表与版本历史的标题、状态来源。
- 按既有版本选择规则最小修复管理列表读取和必要模板：首次送审显示实际标题与“待审核”，同时明确正式发布状态仍为“未发布”；已发布 v1 与待审 v2 并存时同时区分两者；普通草稿仍显示“草稿”。
- 普通员工直访管理列表继续拒绝；员工搜索和详情不得泄露待审内容。不得修改工作流状态机、权限分配、数据库模型、迁移、KB-000001、KB-000002 或其他现有文章。
- 运行管理列表、版本历史、审核和员工读取权限相关回归，以及 Django check、Ruff、git diff --check；可复用 18016 临时隔离环境浏览器验证，否则如实记录浏览器待验。本阶段不暂存、提交、推送、部署、Merge、Reset、Clean、Stash。

### 当前进展

- 2026-11-17：已完成合成数据复现、最小读取修复与回归验收。根因是提交审核服务按既有状态机清空 `latest_working_version`，而列表此前仅从工作版本和正式发布版本取标题；首次送审时两者均为空。列表现按版本号倒序投影唯一 `IN_REVIEW` 版本，标题优先级为工作版本、待审版本、正式发布版本、占位提示；模板独立显示“当前待审版本”，正式发布状态保持原有来源。
- 自动化：管理列表、版本历史、审核和员工读取相关回归 `83 passed、94 subtests passed`；Django check、Ruff lint/format、`git diff --check` 通过。
- 浏览器：复用 `http://127.0.0.1:18016/` 的独立临时环境；编辑员实测首次待审显示真实标题、`v1 · 待审核`、`未发布`，已发布 v1 加待审 v2 显示待审 v2 与已发布 v1；合成员工直访 `/manage/knowledge/` 显示权限拒绝，Web 日志为 `403`。未访问、修改或连接 8001、18443 及其数据库。
- 本任务代码、模板、测试和登记均保持未暂存、未提交、未推送、未部署，供负责人验收。

### 上一任务 `PILOT-HOME-ROLE-NAV-01` 历史记录（`DONE / PASS`，提交 `e3531e522f0b3cef706418b91f0a21e3b016210f`）

- 2026-11-17：首页导航使用知识管理列表 Reader 与审核列表 Reader 的既有身份、角色和权限解析；编辑员只见“知识管理”，审核员只见“待审核知识”，双权限账号同时可见，普通员工不显示任一入口。
- 2026-11-17：专项测试同时核验入口链接与目标页面响应：编辑员可进入 `/manage/knowledge/`、审核员可进入 `/manage/reviews/`，普通员工直访两个地址仍为 `403`；未登录与停用账号首页仍为 `401`，不渲染管理入口。
- 2026-11-17：已在临时隔离浏览器环境 `http://127.0.0.1:18016/` 完成真实页面验收。该环境使用当前工作区只读挂载和独立 Docker 网络、PostgreSQL 测试库及 `dev_employee`、`dev_editor`、`dev_reviewer` 合成身份；容器内首页模板和 `static/css/opsai.css` 与工作区 SHA-256 一致。编辑员首页仅显示“知识管理”并实际进入 `/manage/knowledge/`；审核员仅显示“待审核知识”并实际进入 `/manage/reviews/`；普通员工不显示两个入口，浏览器直访两个地址均由 Web 访问日志核实为 `403`。390×844 窄视口截图确认退出登录换行后完整可见、未被遮挡；已恢复默认视口。未访问、修改或连接 8001、18443 及其数据库。

### 上一任务 `PILOT-LEADERSHIP-DEMO-KNOWLEDGE-01` 历史记录（`DONE / PASS`，仅保留）

- 2026-11-17：在已核验的 `opsai-pilot-baseline-validation-01` 隔离数据库中，按既有创建、提交、独立审核发布服务新增并发布 `KB-000003` 至 `KB-000012` 共 10 篇脱敏中文知识；`KB-000001` 与 `KB-000002` 保持未修改。
- 2026-11-17：现有启用知识空间与 `Printer Support` 分类被复用，未新增或修改分类、角色、账号权限、业务代码、钉钉配置或其他环境。
- 2026-11-17：`pilot_employee_01` 实测“打印不出来”“无法上网”“共享盘打不开”“Excel 文件被占用”“钉钉会议没声音”“远程桌面连不上”“ERP 网页打不开”均可搜索并打开对应详情；一篇待审核文章在批准前已实测对员工搜索与详情均不可见。最终待审核文章数为 0。

### 上一任务 `PILOT-PC-KNOWLEDGE-FEEDBACK-01` 历史记录（`DONE / PASS`，仅保留，不扩大原单篇验收范围）

- 2026-11-15：已确认 `127.0.0.1:18443` 的 Caddy、Web 和数据库均属于运行中的 `opsai-pilot-baseline-validation-01`，且 `pilot_employee_01` 不存在。
- 2026-11-15：在 Web 容器内通过数据库只读事务查询，现有“普通员工”系统角色数量为 `0`。该角色是创建账号的必要既有配置；本轮未创建账号、未新增角色、未修改其他数据。
- 2026-11-15：项目负责人明确批准唯一例外：仅初始化缺失的“普通员工”系统角色，并创建 `pilot_employee_01`；仍禁止初始化其他角色、管理员、开发身份或演示数据。
- 2026-11-15：已只读核对项目既有定义：`ROLE_EMPLOYEE` 名称为“普通员工”、权限集合为空；`sync_system_roles` 会同步四个角色，`create_dev_users` 会同步角色并创建四个开发身份，均不符合本轮范围。
- 2026-11-15：在 `web` 容器的单一数据库事务内，仅创建“普通员工”角色（零权限）及 `pilot_employee_01`。随后以数据库只读事务复核：账号启用、`account_status=active`、`is_staff=False`、`is_superuser=False`、直接权限数为零、仅加入该角色；初始密码不可用，等待项目负责人交互式设置密码。
- 2026-11-15：项目负责人明确授权本轮仅在上述隔离项目完成知识发布到人工反馈前置验收；不得提权 `pilot_employee_01`、不得修改代码、钉钉配置或其他环境。
- 2026-11-15：已在该隔离数据库按现有定义仅初始化“知识编辑员”（9 项既有权限）与“知识审核员”（10 项既有权限），分别创建 `pilot_editor_01`、`pilot_reviewer_01`；两者均启用、非 staff、非 superuser、无直接权限且仅绑定各自角色。未修改 `pilot_employee_01`。
- 2026-11-15：已创建本任务最小员工知识空间、打印机分类及 `pilot_reviewer_01` 的启用审核范围；通过 `create_article`、`submit_article_for_review`、`approve_and_publish_article_version` 服务完成《打印机显示脱机怎么办》（`KB-000001`）的创建、提交、独立审核与发布，未直接修改发布状态。
- 2026-11-15：发布前已验证 `pilot_employee_01` 对该文章不可见、不可搜索；发布后数据库只读核验已发布版本、审核通过记录、员工可见、搜索和详情读取均为真。当前该员工对该文章的反馈记录数为 `0`，等待项目负责人在电脑版钉钉实际选择反馈按钮。
- 2026-11-15：项目负责人已在电脑版钉钉完成 `KB-000001` 反馈。随后仅在对应隔离 Web 容器内以数据库只读事务核验：该文章当前版本为已发布；反馈记录共 `2` 条，均关联 `pilot_employee_01` 与该当前已发布版本。验收收口为 `DONE / PASS`。

## 3. 前一任务状态：PILOT-EMPLOYEE-LOGIN-TEST-01（保留）

- `pilot_employee_01` 已创建并通过最小权限核验；其交互式密码仍由项目负责人自行设置。本任务不得重置、修改或提权该账号。

## 4. 前一任务归档：PILOT-CHROME-LOCAL-CA-01（保留）

- 2026-11-15：仅替换 `opsai-pilot-baseline-validation-01-caddy-1`；`web` 与 `db` 容器 ID、运行状态和启动时间均保持不变，`127.0.0.1:18443` 保持绑定。原 Caddy 容器以 `opsai-pilot-baseline-validation-01-caddy-rollback-20261114` 停止保留，可用于本轮回退。
- 2026-11-15：Caddy 使用仓库外 `D:\Temp\OpsAI-Pilot-Production-Baseline-01\chrome-local-ca-01\Caddyfile` 的 `tls internal`，根 CA 继续持久化在既有 `opsai-pilot-baseline-validation-01_pilot_caddy_data` 卷；仅导出公开 `root.crt`，未导出私钥。
- 2026-11-15：公开根证书的 X.509 SHA-256 指纹为 `5B:5A:D4:24:03:68:EC:C5:4F:C5:23:72:DD:64:45:B8:9A:7E:AB:74:B0:97:CE:E3:8B:31:50:CF:F2:01:12:74`；使用 WSL OpenSSL curl 的 `--cacert` 完整验证 `https://pilot-baseline.test:18443/health/live` 返回 HTTP 200 与 `{"status": "ok", "service": "opsai-it"}`。
- 未导入 Windows 证书库、未使用 `-k` 或其他 TLS 校验绕过参数；Windows Schannel curl 的吊销状态查询在未信任内部根证书时返回预期错误，未作为成功证据。

## 4. 前一任务归档：PILOT-BACKUP-RESTORE-01（保留）

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `PILOT-BACKUP-RESTORE-01` |
| 任务状态 | `DONE / PASS（仅限本地隔离 PostgreSQL 备份恢复演练）` |
| 登记基线 | `d5c1e80f248f492a02428d26a2ac8dcfa74884f1` |
| 功能提交 | `00ab2915d88bd94e516a4caf753b18ff5c3b24d3` |

## 前一任务历史记录：2026-11-11 员工登录离线实施、E2E 与收口

- 已完成：新增正式员工用户名/密码登录与仅限 POST 的退出入口；复用 Django 密码哈希、认证及会话轮换，不提供公开注册、账号自动创建或权限提升。
- 安全边界：禁用、离职及非激活账号拒绝登录；`next` 仅接受当前站点安全路径；登录失败按经 SHA-256 处理的来源地址/用户名组合限流；生产设置继续硬关闭 `/dev/login/` 并启用 Secure、HttpOnly、SameSite 会话与 CSRF Cookie。
- 实际离线验证：专项认证测试 `13/13` 通过；accounts、钉钉适配、员工阅读/反馈及搜索相关回归 `224/224` 通过；`manage.py check`、`makemigrations --check --dry-run`、Ruff lint、格式检查、compileall 与 Git 差异检查通过。Django 模板由渲染测试验证，不以 Python Ruff 解析模板。
- 已执行：`opsai-login-e2e-01` 独立 PostgreSQL/媒体卷与 `127.0.0.1:18015` 隔离部署成功；数据库卷未重建、未重跑迁移或种子。容器内 PostgreSQL 认证专项 `13/13` 通过；只读核验 `KB-000001` 的合成员工反馈为唯一 `resolved` 记录，关联已发布版本。
- 已获补充授权：`templates/base.html` 仅可用于补充正式员工的 POST + CSRF 退出入口；不得改变其他导航、业务逻辑或认证边界。
- 浏览器验收：真实浏览器完成桌面 `1280×720` 与手机 `390×844` 的登录、首页退出入口、搜索、详情、反馈区、POST 退出及退出后受保护首页/详情拒绝；手机两页 `scrollWidth == clientWidth == 375`，未见横向溢出。匿名登录页不显示退出入口。验收截图、导航与哈希保留于 `D:\Temp\OpsAI-Login-E2E-01\evidence`。
- 功能提交：`d26c27f877964f6c506a247900fe58f1aaed65a7`。本任务仅代表本地隔离试点登录 PASS；真实钉钉、真实 ITSM、生产部署和真实员工凭据仍未授权、未验证。

## 前一任务历史记录

## 2026-11-11 阻塞记录

- 阶段：隔离镜像构建（阶段 01：隔离部署）。
- 结果：`BLOCKED / NOT DONE`。Docker 构建 `opsai-feedback-e2e-01-web:323eea2` 时，`pip install --no-cache-dir .` 多次访问 PyPI 超时，无法获取构建隔离所需的 `setuptools>=77`。
- 影响：未创建本轮容器、数据卷或数据库；未执行迁移、合成数据、PostgreSQL 验证或浏览器验收，故不得声明 E2E PASS。
- 证据：`D:\Temp\OpsAI-Feedback-E2E-01\build.stdout.log`、`D:\Temp\OpsAI-Feedback-E2E-01\build.stderr.log`，以及 `.ai/reports/employee-feedback-e2e-01.md`。
- 恢复门槛：负责人确认可用且受控的 Python 构建依赖源或预构建镜像后，以新的明确执行授权重新进行隔离部署；不得以本次阻塞记录自动重试。

## 2026-11-11 人工浏览器补验与收口

- 验收方式：`MANUAL BROWSER E2E`（项目负责人使用 Chrome 人工操作；不是自动化浏览器测试）。
- 证据：`D:\Temp\OpsAI-Feedback-E2E-01\evidence\manual\01_feedback_article_page.png` 与 `02_service_redirect_health_live.png`；两张 PNG 的 SHA-256 已与同目录 `SHA256SUMS.txt` 逐项核对一致。
- 结果：人工操作显示已发布知识 `KB-000001` 的“仍未解决？提交 IT 服务申请”入口，实际导航至受控隔离目标 `http://127.0.0.1:18014/health/live`，页面显示 `{"status": "ok", "service": "opsai-it"}`。
- 既有证据复核：PostgreSQL 专项测试 10/10 PASS；隔离数据库只读核对确认 `resolved`、`unresolved` 各一条，均关联 `dev_employee` 与当前已发布版本，重复反馈保持幂等。
- 历史保留：此前浏览器自动化客户端的 `ERR_BLOCKED_BY_CLIENT` 仅为自动化工具限制，仍保留在验收报告中；本次人工补验满足最终浏览器跳转证据要求。
- 边界：仅验证本地受控 `/health/live` 跳转；真实 ITSM、真实钉钉及生产环境均未验收、未调用。

## 3. 已替换的员工反馈开发任务证据（历史保留）

- `EMPLOYEE-RESOLUTION-FEEDBACK-MVP-01`：`DONE / AUTOMATED ACCEPTANCE PASS`，功能提交为 `e16125c4329a366a88f872cd90e4de5058373dd5`，收口提交为 `cc6215c114b469bb06afe2d91bbaa78e42f43981`。
- 专项与相关回归 61 项通过；全量隔离测试 801 项通过、23 项跳过；真实浏览器、ITSM 与生产环境当时均未验证。

## 4. 已替换的钉钉离线任务证据（历史保留）

- `DINGTALK-H5-SSO-MVP-01`：`DONE / OFFLINE IDENTITY FLOW PASS`，功能提交为 `967283d9a795a7dd146bd89d1e7295b96eb67e8c`。
- 离线专项 14 项通过；全量离线回归 791 项通过、23 项跳过；真实钉钉 SSO 仍为 `NOT VERIFIED`。

## 5. 钉钉后续需单独授权的实施目标（历史规划）

1. 实现钉钉 H5 受控入口：授权码一次性提交到服务端，服务端换取可信身份后创建 Django Session 并恢复安全目标页。
2. 按 `(corp_id, user_id)` 映射既有 `accounts.User`，核验账号状态、组织关联和既有知识受众过滤；不得创建权限绕过。
3. 登录失败、身份缺失、企业不匹配、禁用账号和重放授权码必须失败关闭，不泄露 Token、AppSecret 或员工敏感信息。
4. 保持开发模拟登录入口的现有安全边界：只在 DEBUG 与显式开关同时开启时可用，生产设置必须继续硬关闭。
5. 先完成本地模拟与无凭据单元测试；真实钉钉测试环境仅在负责人提供受控测试租户和独立凭据注入方案后另行验收。

## 6. 钉钉拟议实施范围与停止条件（历史规划）

拟议实现仅限钉钉适配层、其测试、必要的路由接线以及在确有映射缺口时最小的 `accounts` 服务/测试调整。具体可修改文件必须在下一轮实施授权中逐项白名单化；本登记不授权任何代码文件。

- 不扩大到通讯录全量同步、工作通知、回调、生产部署或服务台集成。
- 不得读取、复制、输出或提交 `AppSecret`、Access Token、授权码、Cookie、`.env` 或其他凭据。
- 没有独立测试租户、企业标识、回调白名单、HTTPS/域名方案及受控凭据注入时，不得进行真实钉钉调用。

## 7. 当前安全边界

- `TASK13-REVIEW-WEB-E2E-01`：`DONE / PASS`；证据报告为 `.ai/reports/task13-review-web-e2e-acceptance.md`，不改变 Task 13 主任务状态。
- Task 12 保持 `PAUSED / IN_PROGRESS HISTORY PRESERVED`；Task 13 保持 `BACKLOG / unassigned`。
- 禁止触碰 `opsai-local-demo-web-1`、`opsai-local-demo-db-1`、`opsai-local-demo-postgres-data` 和 `opsai-local-demo-private-media`。
- 禁止操作历史 Task 13-07/13-08 工作区与证据；不得读取或修改 `.env`、生产配置或 Autopilot/R9 文件。
- 未经单独授权不得 Push、Merge、Reset、Clean、Stash、部署或启动钉钉功能开发。

## 8. 已替换的前一当前任务登记（历史保留）

`TASK13-REVIEW-WEB-E2E-01` 已在执行基线 `01529d2a23c7e2c46bb81fa984eb838080eeb63f` 完成五阶段隔离 E2E 验收，状态为 `DONE / PASS`。原始证据为 `D:\Temp\OpsAI-Task13-E2E-01\evidence\TEST_EVIDENCE.md`，SHA-256 为 `43B600CEB6410A503276A1DA37534D50BCE2627DA4810253D1A665F921ABF989`。其隔离 PostgreSQL 定向回归为 `114` 项 OK，桌面 `1280 × 720` 及手机 `390 × 844` 真实浏览器验收均 PASS；没有触碰 `opsai-local-demo-*`。Task 13 主任务仍为 `BACKLOG / unassigned`。

## 9. 更早的历史当前任务登记（历史保留）

以下内容保留为 `LOCAL-DEMO-REVIEW-WEB-01` 的历史登记，不再定义当前唯一任务：

# OpsAI Current Task

> `LOCAL-DEMO-REVIEW-WEB-01` 已在授权基线 `176131758efa01658ffe3a9fee5dee517937154a` 上完成代码与离线自动化验收，状态为 `DONE / OFFLINE WEB IMPLEMENTATION COMPLETED`。独立演示环境的浏览器验收尚未执行：Docker Engine 未运行且 `127.0.0.1:8001` 不可达；不得把此结果描述为生产上线或完整浏览器验收通过。当前没有已授权的下一项业务开发任务。
>
> Task 12“开发文章创建、草稿和版本保存”继续保持 `PAUSED / IN_PROGRESS HISTORY PRESERVED`，不标记为 `DONE`、`COMPLETED`、`ACCEPTED` 或 `SYNCED`；Task 13 继续为 `BACKLOG / unassigned`。本登记不启动 Task 12、Task 13 或审核 Web 开发。

## 1. 本轮完成任务

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `LOCAL-DEMO-REVIEW-WEB-01` |
| 任务名称 | OpsAI 审核 Web 页面与本地演示审核闭环 |
| 当前状态 | `DONE / OFFLINE WEB IMPLEMENTATION COMPLETED` |
| 实施权限 | 已由项目负责人单独授权 |
| 实施 HEAD | `176131758efa01658ffe3a9fee5dee517937154a` |
| 治理登记日期 | `2026-10-31` |
| 当前分支 | `fusion/wagtail-poc` |
| G03 登记基线 | `d184033ee06630c1b1e23081c8060eb12848f4dd` |
| 任务目标 | 在不改写既有审核状态机的前提下，为已授权审核员提供待审核列表、审核详情、本人已审核记录以及批准/驳回 Web 操作，使隔离演示环境能够通过真实页面完成审核。 |
| 依赖 | `LOCAL-DEMO-DATA-01` 已完成；复用 Task 13 既有 Reader、Submit/Reject/Approve Service、Reviewer Scope、审计、幂等和 Outbox 语义；Task 13 主任务仍为 `BACKLOG`。 |
| 实现结果 | 新增审核路由、列表、详情、本人已审核记录、提交审核及批准/驳回页面；全部状态变更仍只调用既有 Service。 |

### 1.1 实际实现范围

实际修改 `apps/workflow/views.py`、`apps/workflow/urls.py`、`config/urls.py`、两个审核模板、专项测试，以及知识编辑页的“提交审核”入口和对应页面测试。`apps/workflow/readers.py`、`apps/workflow/services.py` 保持冻结，只作为依赖调用；未修改模型、Migration、CSS、Docker、`.env` 或持久数据库。

### 1.2 实际验收

1. 专项与关联测试 `51 passed`、`118 subtests`，工作流测试 `94 passed`、`14 skipped`、`130 subtests`，全量离线回归 `846 passed`、`23 skipped`、`712 subtests`。
2. Ruff、格式检查、Python 编译、Django check 和差异检查通过；迁移 dry-run 未发现模型变更，但默认 PostgreSQL 未运行导致连接超时警告。
3. 浏览器桌面及 `390 × 844` 验收为 `NOT TESTED`：Docker Engine 未运行，独立 `opsai-local-demo` 不可达；恢复隔离环境后须单独执行，不得自动启动。

## 2. LOCAL-DEMO-DATA-01 完成归档

| 项目 | 归档结果 |
| --- | --- |
| 任务 | `LOCAL-DEMO-DATA-01` - OpsAI 独立演示环境搭建与第一篇知识文章业务闭环验收 |
| 状态 | `DONE / LOCAL DEMO ACCEPTANCE COMPLETED` |
| 实现 Commit | `d184033ee06630c1b1e23081c8060eb12848f4dd`；父提交 `04d9cea907d3b35e143a3475568aa05291115243` |
| 实现范围 | 新增独立 Compose、演示配置样例、正式 Service 编排命令、10 项安全测试及操作 SOP，共五个文件 |
| 自动验证 | 初始化命令测试 `10 passed`；正式 `apps/tests` 回归 `837 passed`、`23 skipped`、`712 subtests`；Ruff、格式、Python 编译、Compose 解析、Django check 与 `git diff --check` 通过 |
| 运行验收 | `opsai-local-demo` 独立环境 live/ready 均为 200；首页、搜索、正式详情、未登录和无权隔离已用浏览器验证；演示数据库备份恢复成功 |
| 业务证据 | 通过正式 Service 完成创建、保存、提交、独立审核、批准发布；重复初始化保持幂等，外部通知发送次数为 0 |
| 明确边界 | 本表记录 DATA-01 完成时审核页面尚未实现；本轮已补足离线 Web 实现。全仓裸跑的 16 个可选 Wagtail 实验收集错误未改写为通过；本地演示不等于生产上线 |
| 原环境保护 | 实现 Commit 只新增五个授权文件；未修改原业务数据库、容器、数据卷、账号或既有业务代码 |

## 3. LOCAL-DEMO-READONLY-01 完成归档

| 项目 | 归档结果 |
| --- | --- |
| 任务 | `LOCAL-DEMO-READONLY-01` - OpsAI-IT 本地知识库数据及功能只读验收 |
| 状态 | `PASS / READ-ONLY ACCEPTANCE COMPLETED` |
| 验收执行基线 | `60408cdda7a281066eb1cd043e91ff13a2d7e005` |
| 运行环境 | Docker、PostgreSQL 与 Django 正常；当前迁移全部已应用；Web 容器通过 bind mount 使用当前工作区代码 |
| 只读保护 | 所有 ORM 统计位于同一个 PostgreSQL `READ ONLY` 事务和连接中；查询前后 `transaction_read_only=on`，连接 PID 保持一致 |
| 业务数据 | 知识空间、分类、文章、版本、审核记录、受众规则和审核范围均为 0；用户为 2 名，系统角色组为 0 |
| 首页为空原因 | 数据库没有知识业务记录，不是旧代码、草稿隔离、受众拒绝或查询异常 |
| 功能边界 | 创建、版本、提交、驳回和批准发布 Service、员工读取与搜索均已存在；本轮已新增受限审核 Web 入口，浏览器验收待独立环境恢复 |
| 健康检查 | `/health/live` 为 200；`/health/ready` 为 503，原因是 `private_media` 目录不存在 |
| 外部影响 | 数据库、账号、源码、治理文件、Git、容器和原备份实际变更均为 0 |

本归档不把尚未实际执行的正向展示、草稿隔离或审核页面闭环标记为 PASS。审核服务层存在不等于审核 Web 页面已经实现，也不等于当前环境已经具备领导演示条件。

## 4. DATA-01 已核实依赖与现有能力（历史实施合同）

1. `deploy/compose.yaml` 固定项目名 `opsai-it`，映射 `127.0.0.1:5432` 与 `127.0.0.1:8000`，使用 `postgres_data` 卷，并让 Web 读取仓库根 `.env`；DATA-01 不得直接复用该 Compose 合同。
2. `config.settings.development` 已从环境变量读取 PostgreSQL 连接并支持受控开发登录；`MEDIA_ROOT` 固定为 `/app/private_media`。独立 Compose 通过专用环境变量与独立媒体挂载即可复用现有设置，不需要修改 `base.py` 或 `development.py`。
3. `deploy/Dockerfile` 已排除真实 `.env` 构建上下文并以 UID 10001 运行 Web；DATA-01 应从精确、干净的授权 HEAD 构建镜像，不挂载仓库源码，不修改现有 Dockerfile。
4. `create_dev_users` 可在空的开发数据库中同步四个系统角色并创建固定的不可用密码开发身份；`seed_demo_data` 可幂等创建部门、内容用户组、空间、分类及员工关联，但不会创建文章、审核范围或发布数据。
5. 文章创建、版本保存、提交和批准发布应分别复用 `create_article`、`manual_save_draft`、`submit_article_for_review` 与 `approve_and_publish_article_version`；不得修改这些已建立的安全关键 Service 或绕过其权限、锁、幂等、审计与 Outbox 语义。
6. `ReviewerSpaceScope`、系统角色、空间、分类、文章受众、审核记录、审计、幂等与 Outbox 模型均已存在。DATA-01 时审核仅可在隔离数据库中通过现有 Service 完成；本轮已在不改写这些能力的前提下补足 HTTP/UI。
7. 当前代码只在业务事务中生成待处理 `WorkflowOutboxEvent`；未发现 Outbox Worker、邮件、Webhook 或钉钉发送客户端。独立 Compose 仍必须只启动数据库与 Web，不注入外部通知凭据，并在验收时证明实际外部发送次数为 0。

## 5. 独立演示环境冻结合同（历史实施合同）

DATA-01 后续只能在下列隔离身份全部实际回读一致后写入：

| 资源 | 冻结要求 |
| --- | --- |
| Compose Project | 精确为 `opsai-local-demo` |
| Web 地址 | 精确为 `http://127.0.0.1:8001/`；不得占用或代理原网站 8000 |
| 数据库 | 新建空 PostgreSQL 17 数据库；数据库名必须使用 `opsai_local_demo` 前缀，使用独立演示角色和独立随机凭据 |
| 数据库端口 | 不向宿主机发布 5432；Web 只通过独立 Compose 网络访问 `db:5432` |
| 容器 | 只能创建 `opsai-local-demo-*` 容器；不得重建、重启、进入或复用 `opsai-it-db-1`、`opsai-it-web-1` |
| 数据卷 | 只能创建 `opsai-local-demo_*` 命名卷；不得挂载或引用 `opsai-it_postgres_data` |
| 网络 | 使用 `opsai-local-demo` 独立网络；运行期不得加入原 `opsai-it` 网络，计划配置为无外部通知出口的最小网络 |
| 源码 | 从负责人批准的精确、干净 Git HEAD 构建镜像；演示容器不 bind mount 项目工作区 |
| 媒体目录 | 独立挂载到容器 `/app/private_media`，实际验证 UID 10001 可写和 `/health/ready` 为 200；不得复用项目现有 `private_media` |
| 配置 | 仅从独立、未跟踪的演示配置注入变量；不得读取、复制或修改仓库根 `.env`，不得注入真实钉钉、邮件、Webhook 或企业凭据 |

后续允许新建的外部资源候选范围仅为：

- `D:\Temp\OpsAI-Local-Demo\Config\local-demo.env`：未跟踪演示配置，只保存本地随机测试凭据；
- `D:\Temp\OpsAI-Local-Demo\private_media\`：独立演示媒体目录；
- `D:\Temp\OpsAI-Local-Demo\evidence\`：脱敏验收证据与浏览器截图；
- `D:\OpsAI-Backups\Database\LocalDemo\`：独立演示数据库备份及恢复演练文件。

创建任何资源前必须核对同名容器、网络、卷和目录是否已存在。存在未知残留时立即停止，不得清理、覆盖、复用、改名绕过或触碰原迁移前备份 `D:\OpsAI-Backups\Database\OpsAI_迁移前备份_20261029-222705.dump`。

## 6. DATA-01 数据准备与闭环顺序（已执行）

1. 完成精确 HEAD、工作区和独立 Compose 渲染检查；启动前确认渲染配置中没有原容器、原卷、8000、宿主机 5432、根 `.env` 或外部通知凭据。
2. 创建独立数据库、媒体资源和 Web 容器，应用当前迁移；迁移只允许落到新建空演示数据库。
3. 在空演示库中执行 `create_dev_users` 与 `seed_demo_data`，得到编辑者、独立审核者、普通员工、知识管理员、空间和分类。
4. 新的受控演示命令必须验证 `DEBUG=True`、开发登录已开启、独立演示标记、数据库名称、数据库主机和固定演示身份；任一不符时在写入前失败关闭。
5. 创建审核者空间范围；使用编辑者调用 `create_article` 创建《网络打印机无法打印——故障排查 SOP（演示）》及首个 DRAFT，并建立与普通员工匹配的明确受众规则。
6. 使用 `manual_save_draft` 固化一个 `SAVED` 历史并产生新 DRAFT；再依次调用 `submit_article_for_review` 和 `approve_and_publish_article_version`，每个动作使用独立固定格式的幂等键。
7. 独立审核者不得是文章创建者或提交者；批准后必须核对 ReviewRecord、PUBLISHED 指针、后继 DRAFT、AuditEvent、幂等记录和待处理 Outbox。
8. 使用普通员工完成首页、搜索和详情正向验收，并验证未登录、无权限、DRAFT 与 `SAVED` 历史不泄露。
9. 演示命令首次执行允许创建；再次执行只允许在最终状态和摘要完全一致时做只读确认。任何偏差、半完成状态或不确定结果必须停止，不得自动补写、重新提交或再次批准。
10. 审核 Web 页面已经离线实现；不得用自动化测试冒充尚未执行的独立环境浏览器点击验收。

## 7. DATA-01 精确文件白名单（已实施）

以下五个文件已由实现 Commit `d184033ee06630c1b1e23081c8060eb12848f4dd` 新增；本表保留原实施白名单及用途：

| 文件 | 用途 |
| --- | --- |
| `deploy/compose.local-demo.yaml` | 定义 `opsai-local-demo` 的独立 db/web、8001 端口、独立卷/网络/媒体挂载和零外部通知运行边界 |
| `deploy/local-demo.env.example` | 只列出演示变量名、占位值和安全说明；不得包含真实凭据 |
| `apps/knowledge/management/commands/seed_local_demo_article.py` | 只编排现有角色、数据和正式业务 Service，建立一篇演示文章闭环；不得复制状态机逻辑 |
| `apps/knowledge/tests/test_seed_local_demo_article.py` | 覆盖隔离门禁、权限、顺序、幂等、冲突失败关闭、记录数量和零通知发送 |
| `docs/06-Process/LOCAL-DEMO-DATA-01-SOP.md` | 记录启动、隔离回读、迁移、数据准备、浏览器演示、备份恢复与安全停止步骤 |

经本轮代码核实，DATA-01 不需要修改 `deploy/Dockerfile`、`.gitignore`、`config/settings/base.py`、`config/settings/development.py`、现有 `create_dev_users` / `seed_demo_data`、Grant/审核状态机、模板或 CSS。若后续实际实施证明必须修改现有文件或增加第六个仓库文件，必须停止并提交精确证据申请追加授权，不得自行扩大范围。

## 8. DATA-01 验收标准（已按归档证据完成）

1. `docker compose config` 与 Docker inspect 证明 Project、容器、镜像、数据库身份、网络、卷、端口、媒体目录和源码 HEAD 全部属于 `opsai-local-demo`。
2. DATA-01 前后分别证明原 8000 网站、`opsai-it-db-1`、`opsai-it-web-1`、`opsai-it_postgres_data` 和原备份身份、状态及摘要未变化。
3. 独立演示数据库从空库迁移成功，且只包含本任务预期的演示身份、业务记录和系统生成证据。
4. 独立 `private_media` 可写，`/health/live` 与 `/health/ready` 均返回 200；不得跳过媒体检查或修改健康检查强制返回成功。
5. 演示角色、编辑者、独立审核者、普通员工、知识管理员及 Reviewer Scope 符合最小权限设计，没有可用密码或真实钉钉身份。
6. 演示文章由正式 Service 创建、保存、提交、批准与发布；不得直接 UPDATE 状态、指针、审核结论或受众权限。
7. 普通员工在首页、搜索和详情页能看到正式文章；未登录、无权身份、DRAFT 和 `SAVED` 历史不能泄露。
8. 版本、审核、审计、幂等和 Outbox 记录与服务合同一致；重复命令不产生第二篇文章、第二次批准或重复通知。
9. 实际外部通知发送次数为 0；只允许保留未消费的本地 Outbox 证据，不启动 Worker。
10. 自动测试、Django check、迁移一致性、Compose 配置检查、静态检查和 `git diff --check` 全部通过。
11. 完成桌面及 `390 × 844` 浏览器验收并保留脱敏证据；本轮因 Docker Engine 未运行而未执行。
12. 形成独立演示数据库备份并完成一次恢复验证；恢复资源仍必须属于 `opsai-local-demo`，不得覆盖当前演示库或原数据库。
13. 完成可重复启动、演示、停止和恢复 SOP；停止操作默认保留演示数据卷，任何删除卷动作须另行人工确认。

## 9. DATA-01 历史停止条件与当前禁令

出现以下任一情况，后续实施必须在写入前停止：精确 HEAD、分支或工作区不符；同名资源已存在；渲染配置引用原 `.env`、原容器、原网络、原卷、8000 或宿主机 5432；无法证明数据库为空且独立；媒体目录不可写；开发身份或演示数据发生冲突；外部通知能力已启用；需要修改候选白名单外文件；任何业务调用结果不确定。

后续任何新任务获得独立授权前继续禁止：

- 创建、启动、停止或重建任何 Docker 资源；
- 连接或写入任何数据库，执行 Migration，创建账号、角色、空间、分类、文章或审核记录；
- 读取、复制或修改根 `.env` 及任何真实凭据；
- 修改业务代码、测试、Compose、设置、模板、CSS、`AGENTS.md` 或 `tasks/TASKS.yaml`；
- 启动真实通知、钉钉、邮件、Webhook、Autopilot LIVE，或执行 Push、Merge、Reset、Clean、Stash；
- 重复执行 DATA-01、自动启动后续任务、恢复 Task 12 或启动 Task 13。

## 10. 历史治理记录（以下原章节编号与证据保持原样）

## 4. Task 12 暂缓状态与历史身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `Task 12` |
| 任务名称 | 开发文章创建、草稿和版本保存 |
| 优先级 | `MUST`；因本地演示只读验收优先而暂缓 |
| 当前状态 | `PAUSED / IN_PROGRESS HISTORY PRESERVED`；Task 12A～12E 已完成，主任务最终封板条件仍未满足 |
| 当前负责人 | `codex`；暂停期间不得自动继续 |
| 原治理登记日期 | `2026-10-25` |
| 暂缓登记日期 | `2026-10-29` |
| 局部例外 | Task 13-08 核心修复与 Task 13-08-ARCHIVE 归档已完成；二者不代表 Task 13 全面开工或完成 |
| 原治理起始 HEAD | `a066b8e158d53770b2f9dab5e2c7e70c87817975` |
| PG07 归档证据 | Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 仅新增 `apps/workflow/tests/test_pg_concurrency.py`；父提交为 `8049e17eabf97148b42a6c6b0196ac098bf1613c` |
| 正式任务状态 | Task 12 保持未完成；Task 13 保持 `BACKLOG / unassigned` |
| 已完成核心修复 | Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 从 Submit/Reject 的 Article 加锁查询中移除可空 `current_published_version` 联表，只保留 `space` |
| 已归档 PG07 | `apps/workflow/tests/test_pg_concurrency.py` 已纳入 Git；SHA-256 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`，Git 提交统计新增 993 行 |
| 历史原始版本 | 归档前原始文件 SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`，已在独立 Evidence 目录备份 |
| P3-UI-02 | 下一项试点候选；不是 `READY`，不是当前任务，未获执行授权 |
| 恢复条件 | 如需恢复 Task 12，由负责人基于届时完整 HEAD 单独决定；DATA-01 完成不构成自动恢复授权。 |

## 5. Task 12 已完成阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 12A | 正式写入契约与融合范围冻结 | `DONE / SYNCED` |
| 12B | 最小 Model / Migration 增量 | `DONE / SYNCED` |
| 12C | KB 编号服务与原子 Article 创建 | `DONE / SYNCED` |
| 12D | autosave、manual save、版本链与历史恢复 | `DONE / SYNCED` |
| 12D-00 | SAVED `full_clean` 与数据库约束一致性修复 | `DONE / SYNCED` |
| 12D-01 | 版本写入状态机、乐观锁与历史恢复设计审计 | `DESIGN PASS` |
| 12D-02 | autosave CAS 与公共版本写入合同 | `DONE / SYNCED` |
| 12D-03 | manual save、`version_no` 与历史不可变收口 | `DONE / SYNCED` |
| 12D-04 | history restore 与管理侧版本历史 Reader | `DONE / SYNCED` |
| 12D-05 | 版本链综合 SQLite 收口验证 | `DONE / SYNCED` |
| 12D-06 | PostgreSQL 真实并发补证 | `DONE / SYNCED` |
| 12E | 正式管理编辑页面、草稿预览与浏览器验收 | `DONE / ACCEPTED` |
| 12E-02～12E-08 | 管理列表、Create、Draft 编辑、Autosave、Manual Save、History/Restore、Draft Preview | `DONE / SYNCED` |
| 12E-09A | 真实 Chromium 完整管理链与视觉验收 | `PASS_WITH_VISUAL_FINDINGS` |
| 12E-09B | Task 12E 验收文档与状态收口，Commit `411535b32db4a40991e3c64228d018e9cebb17ed` | `DONE` |
| 13-08 | PostgreSQL 可空关联行锁最小修复，Commit `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` | `DONE` |
| 13-08-001 | 原始 PG07 夹具 PostgreSQL 复验：13 PASS、1 FAIL | `FAILED / EVIDENCE PRESERVED` |
| 13-08-002 | 修正 PG07 夹具 PostgreSQL 复验：14 PASS、0 FAIL | `PASS / EVIDENCE PRESERVED` |
| 13-08-ARCHIVE | PG07 已验证修正夹具单文件归档，Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` | `DONE` |

## 6. Task 12D 交接摘要

- autosave 使用 `expected_lock_version` 做乐观 CAS；过期 token 明确冲突，不采用 last-write-wins。
- manual save 将 `DRAFT(n)` 固化为不可变 `SAVED(n)`，并创建新的工作 `DRAFT`。
- 后续 `version_no` 在 Article 行锁保护下按现有最大版本号加一生成。
- 正式 Writer 与 Admin 均不能修改 `SAVED` 历史。
- restore 不修改来源历史，而是创建新 `DRAFT`；`restored_from_version` 保留恢复血缘。
- Task 12D 不改变 `current_published_version`；员工读取仍只使用正式 `PUBLISHED` 版本。
- SQLite 版本链整体验证通过；PostgreSQL 17.11 真实并发验证通过。

## 7. PostgreSQL 证据边界

Task 12D-06 在 PostgreSQL 17.11 仓库外临时隔离环境完成验证：端口 `15432`、存储为 `tmpfs`，六类真实竞争与 Lock wait 均为 PASS，临时验证资源已完全清理。

该证据不等于 8J 的真实持久 PostgreSQL 验证，不证明正式数据库或生产环境已经验收。真实 `.env` 的内容、来源、完整性和适用性仍未验证；8J 继续为 `BLOCKED / unassigned`。

## 8. Task 12E 完成与验收摘要

Task 12E 已完成以下范围：

1. 正式编辑器 UI 与草稿编辑入口；
2. 接入 autosave / manual save Service；
3. 历史版本查看与恢复入口；
4. 草稿预览；
5. 保持员工正式发布内容隔离；
6. 完成真实 Chromium 管理主链、Employee 隔离与双标签 CAS 验收。

Task 12E 累计自动化证据为 `717 passed`、`9 skipped`、`571 subtests`、`0 failed`；Django check、迁移一致性、Ruff、Format、`git diff --check` 与 `node --check` 均 PASS。Task 12E-09A 真实浏览器结论为 `PASS_WITH_VISUAL_FINDINGS`，P0/P1/P2 均为 0，P3 为 2。详细证据见 `docs/06-Process/Task12E-管理端知识编辑链验收.md`。

两项 P3 分别为 Create 表单视觉一致性和 Edit 页“预览草稿”/“保存版本并继续编辑”操作层级，均为 `BACKLOG / non-blocking`，本轮不修复。窄屏验收为 `NOT_EXECUTED_BROWSER_CAPABILITY`，不得宣称移动端视觉 PASS。

Task 12E 已 `DONE / ACCEPTED`，收口 Commit `411535b32db4a40991e3c64228d018e9cebb17ed` 已存在于当前历史。Task 12 主任务的历史状态保持 `IN_PROGRESS / codex`，现以 `PAUSED / IN_PROGRESS HISTORY PRESERVED` 暂缓；在负责人最终验收、`390 × 844` 窄屏视觉验收或负责人书面豁免、Gitee 当前远端 HEAD 核验及必要治理同步完成前，不得标记为 `DONE`、`ACCEPTED` 或 `SYNCED`。

## 9. Task 13 既有实现登记

以下提交已逐个核验并保留，但均不等同于正式验收通过：

| Commit | 实际功能 | 历史测试证据 | 当前结论 |
| --- | --- | --- | --- |
| `031a4fca26cebcaf5b67091142ac6b3b82c9cbaa` | Reviewer 空间 Scope、动作权限及审核唯一约束基础 | `735 passed`、`9 skipped`、`582 subtests` | 已有实现，持久 PostgreSQL 迁移前置检查和独立验收未完成 |
| `95af9ca7c06eced103a7a034482959c97df04852` | AuditEvent、Outbox、幂等持久化基础 | `761 passed`、`9 skipped`、`585 subtests` | 已有实现，未连接持久 PostgreSQL，Worker/通知不在实现内 |
| `6d6bb9808ef68b87de63cf1d1762105aa9f8485a` | `DRAFT → IN_REVIEW` 提交审核 Service | `785 passed`、`9 skipped`、`624 subtests` | 已有实现，无 HTTP/UI，真实 PostgreSQL 并发未验收 |
| `e88bf8e065807343a5b78a0a49c29d0824980b67` | 驳回、审核记录、后继 Draft、审计/Outbox/幂等 | `800 passed`、`9 skipped`、`657 subtests` | 已有实现，Approve-vs-Reject 等 PostgreSQL 竞争未验收 |
| `e422b16ba0826064a629604a217b93978101d5f7` | 原子批准发布/重新发布及新工作 Draft | `818 passed`、`9 skipped`、`697 subtests` | 已有实现，双 Reviewer、锁等待和事务隔离未验收 |
| `5bf0632af3dd19163b7ac0fe0f6d126b6a19b19e` | 待审、审核详情、已审核、提交状态、驳回上下文 Reader | `827 passed`、`9 skipped`、`712 subtests` | 已有实现，无 HTTP/UI，尚待独立验收 |

ADR-0004 证明负责人选择了 Reviewer Scope 方案 B，但现有资料未发现六项实现各自完整的历史开工授权或负责人独立验收记录。本轮只确认保留与登记，不改变 Task 13 的 `BACKLOG / unassigned` 状态。

归档前原始文件 `apps/workflow/tests/test_pg_concurrency.py` 的 Git 来源无法确认，SHA-256 为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`。Task 13-08-002 已验证的修正隔离副本 SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`；两个摘要对应不同字节版本。原始版本已在独立 Evidence 目录备份，修正版本已由单文件 Commit `a066b8e158d53770b2f9dab5e2c7e70c87817975` 正式纳入 Git。


## 10. Task 13-07 验收结论与历史现场

### 10.1 001 历史现场（BLOCKED，原样保留）

- 001 在基线 `04e363b5976536de34aede336e49c6747cede521` 上因指定 Worktree 和 Evidence 在资源门禁检查时已经存在而停止；未启动 PostgreSQL、未执行 Migration 或并发测试。
- `D:\Temp\OpsAI-Task13-07-001-Workspace` 保持 detached HEAD `04e363b5976536de34aede336e49c6747cede521`，已跟踪工作区和索引无修改；两个未跟踪文件保持原样。
- `D:\Temp\OpsAI-Task13-07-001-Evidence\preflight.md` 保持原样，SHA-256 为 `F7EB5604523EBEECB155DE69DEE3C3A7884CC6B813B12F3AD897797C8EAF584E`。
- 001 Worktree、Evidence 及其内容不得删除、移动、覆盖、清理、执行或复用。

### 10.2 Task 13-07-002 验收结果（FAILED）

- 运行标识：`TASK13-07-ISOLATED-PG-002`。
- 执行基线：`9fbc74843c339bc712ca59dc67e7bc28e22ef9d8`。
- 实际测试：14 项执行，6 PASS、7 FAIL、1 ERROR、0 SKIPPED；没有重跑。
- 正式结论：`FAILED`。Task 13-07 历史状态继续登记为 `BLOCKED / unassigned`；其暴露的行锁缺陷已有 Task 13-08 后继核心修复及 13-08-002 的 14 PASS 证据，但不得据此改写 13-07 历史结果或自动重跑。
- 已确认 PostgreSQL 错误：`FOR UPDATE cannot be applied to the nullable side of an outer join`。
- 根因：Submit 与 Reject 的 Article 加锁查询使用 `select_related("space", "current_published_version")`；`current_published_version` 为可空关联，使 PostgreSQL 拒绝在该外连接的可空侧应用 `FOR UPDATE`，相关路径返回 `WORKFLOW_UNAVAILABLE`。
- Approve/Publish 的 Article 加锁查询只联表加载 `space`，其主要并发场景通过；本轮缺陷修复不得擅自修改 Approve/Publish。
- 证据来源：`D:\Temp\OpsAI-Task13-07-002-Evidence\execution-results.md` 与 `final-state.md`。002 Worktree、Evidence 和已停止容器均保留用于审计，本轮不得操作、覆盖或清理。
- Task 13-07-002 当时使用的原始测试文件与 002 副本 SHA-256 均为 `08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`；该摘要继续作为历史失败证据保留，不因后续归档而改写。

## 11. Task 13-08 完成证据

### 11.1 核心修复

- 核心 Commit：`1050b8fbf1fc384a79a90fcc86ae9320e5afb67e`。
- 实际修改：`apps/workflow/services.py`、`apps/workflow/tests/test_submit_service.py`、`apps/workflow/tests/test_reject_service.py`。
- 实现内容：从 Submit/Reject 的 Article 加锁查询 `select_related` 中移除 `current_published_version`，只保留 `space`；Article 行锁和事务边界保持不变。
- Commit 内验证：RED 2 项失败、GREEN 2 项通过；Submit/Reject 39 项、审核/权限/幂等及 Approve/Publish 63 项、Task 12 版本链 97 项，共 199 项唯一测试通过。

### 11.2 PostgreSQL 修正夹具复验

- Task 13-08-001：在 HEAD `1050b8fbf1fc384a79a90fcc86ae9320e5afb67e` 使用原始哈希副本执行 14 项，结果为 13 PASS、1 FAIL、0 ERROR、0 SKIPPED；PG07 暴露 Article 初始标题与旧 `PUBLISHED` 版本标题不一致。
- Task 13-08-002：在同一 HEAD 使用可追溯修正副本执行 14 项，结果为 14 PASS、0 FAIL、0 ERROR、0 SKIPPED；原可空外连接行锁错误未再出现。
- 修正副本只调整 PG07 初始 `Article.title` 与当前 `PUBLISHED` 版本标题投影一致性；隔离副本 SHA-256 为 `4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`。
- 上述证据完成 Task 13-08 核心修复验收；正式仓库中的 PG07 测试文件随后由独立归档 Commit 完成纳管，但这仍不等于 Task 13 主任务完成。

## 12. Task 13-08-ARCHIVE 完成记录

该后继任务已在负责人针对精确基线单独授权后完成；以下记录归档边界和可核验证据，不构成再次执行授权。

- 归档 Commit：`a066b8e158d53770b2f9dab5e2c7e70c87817975`；父提交：`8049e17eabf97148b42a6c6b0196ac098bf1613c`。
- 唯一归档文件：`apps/workflow/tests/test_pg_concurrency.py`；Commit 仅新增该文件，Git 提交统计为新增 993 行。
- 已归档 SHA-256：`4C994737B880CDFE1E75391B99C601F94D702F149B4EFBBEB6AC9C500260854A`；与批准来源逐字节一致。
- 归档前原始版本 SHA-256：`08E6DAE26FFD8959592C47FB77BA5604B69A2543308F36CDB855C08D7E143E23`；原始版本已在独立 Evidence 目录备份。
- Python 编译、Ruff lint、Ruff format check 和 Git 检查通过。本次归档没有重新执行 PostgreSQL；14/14 PASS 是 Task 13-08-002 修正副本的历史验证证据。
- 归档没有重复运行或重新实现 Task 13-08 核心修复；此前失败、复验、Worktree 和 Evidence 历史事实保持不变。

继续禁止修改业务实现、其他测试、治理文件以外的文件、历史 Evidence、临时 settings 或数据库文件；禁止 Push、Merge、Reset、Clean，不得自动启动 HTTP/UI 或其他任务。

## 13. 持续边界

- Task 12 历史成果全部保留，主任务以 `PAUSED / IN_PROGRESS HISTORY PRESERVED` 暂缓；尚缺负责人最终验收、`390 × 844` 窄屏视觉验收或书面豁免、Gitee 当前远端核验及必要治理同步，不得标记为 DONE。
- Task 13 主任务继续为 `BACKLOG / unassigned`；Task 13-08 核心修复与 Task 13-08-ARCHIVE 归档均为 `DONE / unassigned`，但不代表 Task 13 全面完成。
- 001 和 002 的 Worktree、Evidence、未跟踪文件与 002 已停止容器必须原样保留，不得覆盖或清理。
- 正式内容权威保持 `Article + ArticleVersion`；Wagtail 尚未进入正式根依赖、settings、路由或正式运行时。
- 正式员工读取继续只走 `current_published_version`，不得暴露草稿、`SAVED` 历史或管理预览。
- 本轮实施未读取真实 `.env`、未连接持久 PostgreSQL、未执行 Migration，也未启动 Docker 或 HTTP 写入；P3-UI-02 继续只是未授权候选，不 Push、Merge、Reset 或 Clean。`docs/HANDOFF.md` 只能用于人工接力，不能授予自动执行权。
