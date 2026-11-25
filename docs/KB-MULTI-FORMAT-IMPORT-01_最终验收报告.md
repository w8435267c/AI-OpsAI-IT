# KB-MULTI-FORMAT-IMPORT-01 最终验收报告

日期：2026-11-25
审查工作树：`D:\Desktop\OpsAI\AI-OpsAI-IT-multi-import`
分支：`feature/kb-multi-format-import-01`
审查基线：`8b982ef994d19fc37806ab49c4f5c17fe33658da`

## 1. 目标和交付范围

本任务实现 DOCX、TXT、Markdown、PDF 的受控导入：文件格式和扫描校验、私有原文件留存、结构化富文本转换、管理端编辑/自动保存、审核发布、员工受众过滤阅读及受控下载审计。

PDF 当前仅支持可提取文本，不承诺还原原始图片、复杂排版或可编辑版式。按 KB 编号搜索仍属于 `SEARCH-ARTICLE-ID-01`，不属于本任务。

## 2. 四格式实现与人工验收

负责人已在 Firefox 完成以下人工验收；本报告将其作为已提供证据，不伪造新的浏览器记录。

| 格式 | 文章 | 已验收内容 |
| --- | --- | --- |
| DOCX | KB-000009 | 图文、表格、图片编辑/恢复、历史、审核发布、员工阅读、移动端、受众隔离、原文件受控下载与审计。 |
| TXT | KB-000010 | 中文换行、操作步骤、编辑保存刷新、审核发布、员工搜索阅读。 |
| Markdown | KB-000011 | 标题、加粗、列表、代码块、表格、HTML 安全处理、发布阅读；发布后的 v2 自动保存、新标签页读取和强制刷新。 |
| PDF | KB-000012 | 双页中文提取和页序、限制提示、审核发布、员工搜索阅读；v2 自动保存和刷新恢复，v1 未被草稿覆盖。 |

最终 Firefox 复验（负责人确认）通过：KB-000009 v2 编辑页可打开，4 张 DOCX 图片及其顺序、说明、宽度和表格正常，强制刷新后仍存在；v1 图文不变；有权员工可阅读；无权已登录员工不能读取正式文章，直接访问受保护媒体显示“未找到可查看的媒体”。该截图没有单独记录 HTTP 状态码，因此本报告不把浏览器状态码写作已验证证据；权限行为同时由自动化媒体读取测试覆盖。

## 3. 自动化与质量检查

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest apps -q`（临时无害配置） | 965 passed，23 skipped，737 subtests passed | 应用测试通过；23 个跳过项为未重建的 PostgreSQL 专项。 |
| P1 媒体专项（批准/驳回、媒体读取、历史、DOCX） | 65 passed，89 subtests passed | 本轮重新执行，通过。 |
| `python -m pytest -q` | 未通过：16 个收集错误 | 误收集 `experiments/wagtail_*` 历史 PoC；当前环境未安装 Wagtail，且若干实验以独立导入方式运行。不是本任务测试失败，但仓库全量 pytest 尚不可作为绿色基线。 |
| `manage.py check --settings=config.settings.test` | 通过 | 无问题。 |
| `manage.py makemigrations --check --dry-run --settings=config.settings.test` | 通过 | `No changes detected`。 |
| `ruff check .` | 通过 | 无 lint 问题。 |
| `ruff format --check .` | 通过 | 仅格式化了本任务相关的 `apps/knowledge/media_services.py` 与 P1 修改文件。 |
| `npm run build:richtext` | 通过 | 重新生成 `static/js/richtext_editor.js`。 |
| `node --check static/js/knowledge_editor.js` / `richtext_editor_source.js` | 通过 | JS 语法通过。 |
| `git diff --check` | 通过 | 仅有 Windows CRLF 工作副本警告，无空白错误。 |

## 4. 隔离环境与数据只读核验

`opsai-multi-import-acceptance-01` 正常：本轮复核 Web、Caddy、PostgreSQL、ClamAV 均运行；`https://localhost:18027/health/live` 返回 200。Web 运行镜像为 `opsai-multi-import-acceptance-01-web:8b982ef-multi-import-local`。Caddy 的富文本 bundle SHA-256 与本地构建完全一致：`cc8bbbab48070d26b04e059b5aab1cbb9c6b461f06944947de2b00fe5a3dd790`。

未输出正文、凭据或私有文件。四篇文章均为 `active`，导入源原文件均为 `document` 且扫描状态为 `clean`，正文格式均为 `opsai.richtext/1`。

| KB | 发布指针 | 工作草稿 | 导入源 | 审核/受众结论 |
| --- | --- | --- | --- | --- |
| KB-000009 | v1 `940f5f8e-4551-46bc-b169-301feb2aa396`，published | v2 `7c34b870-f6d5-4fe6-bb82-20406e02f726`，draft，lock 2 | DOCX 位于 v1 | v1 已批准；`restricted`。v2 的 4 个正文媒体引用全部归属 v2，缺失/跨 v1 引用均为 0。 |
| KB-000010 | v1 `120ae050-42bb-4a48-a793-b9ad9a21d3c3`，published | v2，lock 1 | TXT | v1 已批准；`all_employees`。 |
| KB-000011 | v2 `29bcb3c2-32c2-45a8-812c-85b3bbd4b0e4`，published | v3，lock 1 | Markdown 位于 v1 | v1 已 superseded，v2 已批准；v2 与 v3 的正文摘要哈希一致，显示发布后的草稿未覆盖 v2。 |
| KB-000012 | v1 `3d7bfccc-6263-4a74-87d0-6b6c827c0237`，published | 无 | PDF 位于 v1 | v1 已批准；v2 为 `in_review`、lock 3，正文摘要哈希与 v1 不同，未覆盖 v1。 |

Markdown 与 PDF 的后续版本均保存了非空、与其对照版本可区分的结构化正文和乐观锁状态；结合负责人给出的 Firefox 验收，视为持久化证据。审核记录、发布/草稿指针和导入源关系不存在孤立指针。

## 5. 关键 Bug 与最终状态

已实现并有专项测试覆盖的修复包括：

- 导入后的编辑页按草稿、审核中、已发布无草稿和无权限状态提供正确入口；不在 GET 中创建版本。
- Tiptap 空段落/空单元格与整篇空正文校验区分。
- 自动保存使用最新 structured JSON、CAS 版本号和真实响应状态；保存失败、冲突和离页保护有反馈。
- Tiptap `textStyle` 与服务端 `color` 协议规范化；未知或重复 mark 仍被拒绝，并消除 Link/Underline 重复扩展注册。

### 已修复 P1：发布或驳回后 DOCX 后续草稿的图片关联失配

只读核验显示 KB-000009：v1 的 4 个正文图片引用均能命中同版本关联；v2 草稿有 4 个正文图片引用，但没有命中 v2 的关联 ID，同时存在 9 个未被 v2 正文引用的活动关联。

根因位于 [apps/workflow/services.py](../apps/workflow/services.py)：

- `_create_approved_successor_draft()` 第 1401 行只调用 `copy_active_media_links()`，未使用返回的旧/新 link 映射重写 `successor.body`。
- 被驳回后的后续草稿路径第 981 行同样未重映射。

`ArticleVersionMedia` 每次复制都会生成新 UUID，而结构化正文存的是关联 UUID；因此后续草稿编辑/预览的图片 URL 无法解析，存在发布后继续编辑 DOCX 时图片丢失/不可读的风险。该问题与任务要求的图片节点及媒体关联完整性直接冲突。

已实施的最小修复：新增共用 `_copy_and_remap_successor_media()`，两个工作流克隆路径均获取 `copy_active_media_links()` 的旧/新关联映射，调用既有 `remap_richtext_media_links()` 只重写图片节点引用，并在存在未映射、跨版本或无效引用时安全失败、回滚事务。

新增专项回归：批准路径的两张图片、段落/表格结构、图片属性和 autosave；驳回路径的重映射；两条缺失或跨版本媒体引用的原子回滚。结果：`86 passed, 123 subtests passed`。正式/历史版本正文未被修改。

### KB-000009 v2 既有异常数据（已按授权修复）

新代码仅作用于未来创建的后续草稿，**不会自动修复** KB-000009 v2。负责人已单独授权本次隔离环境数据修复；修复前 v2 为 `draft`、lock 1，有 4 个失效正文引用，所有关联资产为 clean，原受控 DOCX 文件存在。

已验证的 v1 → v2 最小映射为：

| v1 正文关联 UUID | 应替换为 v2 关联 UUID |
| --- | --- |
| `f6915f3a-d437-419d-84ba-1276c12d6c7f` | `6a218a4e-0ae1-45c4-bef9-8f2754b8e744` |
| `6932c8eb-d94a-4998-ac2f-7cb7e93a919b` | `82c429ad-c2fe-473d-9c2a-9227fffd00fb` |
| `bf81645e-1ab1-45d8-8c93-8590a1a1ea44` | `637cccf7-06fc-4562-b9ca-aaa474c1026e` |
| `2bf0eb6b-9007-4da8-b4a6-0adb31333bf7` | `6eb9b718-1d55-48cc-b3ad-8f6999dc8e83` |

实际修复在一个数据库事务内完成：锁定 Article、v1、v2 后再次核验全部前置条件，先写入并校验 v2 快照，再仅替换四个 `media_link_id`，最后将 lock 从 1 递增到 2。实际修改记录数为 1。

- 受控备份：隔离 Web 容器 `/tmp/opsai-kb-000009-v2-pre-media-remap.json` 仍存在；SHA-256：`0d413930ab396bb565c73fb2d0316e8da2b23abe9c01c1ee946223e0be19ede7`。`/tmp` 随容器重建不保证留存；如需保留审计回退材料，应由负责人另行授权导出到受控、非 Git 的隔离证据存储。
- 备份校验：备份 JSON 的正文摘要与写入前 v2 一致；可使用备份中的原正文及反向 UUID 映射在同样的行锁/状态/lock 前置条件下恢复。
- 修复后：v2 保持 `draft`、lock 2；4 个正文引用均属于 v2，无失效或跨版本引用；除四个 UUID 外正文结构与纯文本均未变化。
- v1 不变：published；修复前后正文摘要均为 `dfdd07aa6acc7256b58f648845f590e277ed4427c163e566c0470d5a58e4f832`，四个 v1 正文媒体关联未变化；restricted 受众策略未变化。
- 修复后回归：媒体权限、版本历史、DOCX 导入、批准/驳回工作流共 `65 passed, 89 subtests passed`；`/health/live` 返回 200。

## 6. 安全、权限与审计

- 导入原文件使用私有 `MediaAsset`，扫描通过才可发布/下载；四篇源文件均为 clean。
- 员工读取、媒体和下载仍由服务端受众过滤；KB-000009 保持 restricted 规则。
- Markdown HTML 仅转为安全结构化内容，负责人已验证示例脚本不执行。
- 未发现待提交 `.env`、证书私钥、数据库备份、上传原文件、日志或虚拟环境。`deploy/multi-import-acceptance.env.example` 是变量名示例，不含真实值。

## 7. Git 变更审查与建议暂存清单

审查开始时无暂存文件；P1 修复后共有 55 个任务候选文件。所有候选均属于多格式导入或其验收记录；未发现其他工作树文件或敏感材料。

| 文件 | 目的 | 测试/建议 |
| --- | --- | --- |
| `.gitignore` | 忽略任务生成物 | 纳入 |
| `apps/knowledge/content.py` | 富文本校验、mark 与媒体引用 | 纳入，已测 |
| `apps/knowledge/docx_import.py` | DOCX 图文解析 | 纳入，已测 |
| `apps/knowledge/document_import.py` | DOCX/TXT/MD/PDF 导入编排 | 纳入，已测 |
| `apps/knowledge/import_sources.py` | 私有导入源处理 | 纳入，已测 |
| `apps/knowledge/manage_forms.py` | 导入/编辑表单 | 纳入，已测 |
| `apps/knowledge/manage_readers.py` | 编辑状态读取 | 纳入，已测 |
| `apps/knowledge/manage_urls.py` | 管理路由 | 纳入，已测 |
| `apps/knowledge/manage_views.py` | 导入、编辑、自动保存 HTTP | 纳入，已测 |
| `apps/knowledge/media_services.py` | 媒体扫描/关联/下载 | 修复格式后纳入 |
| `apps/knowledge/models.py` | 导入源模型关系 | 纳入，迁移已核验 |
| `apps/knowledge/readers.py` | 员工阅读富文本 | 纳入，已测 |
| `apps/knowledge/richtext_import.py` | 四格式到结构化富文本 | 纳入，已测 |
| `apps/knowledge/richtext_render.py` | 安全渲染 | 纳入，已测 |
| `apps/knowledge/services.py` | 保存、媒体重映射 | 纳入，已测 |
| `apps/knowledge/version_readers.py` | 版本读取 | 纳入，已测 |
| `apps/knowledge/migrations/0010_articleversion_import_source.py` | 导入源迁移 | 纳入，迁移已核验 |
| `apps/knowledge/tests/test_content.py` | 富文本协议测试 | 纳入 |
| `apps/knowledge/tests/test_docx_import.py` | DOCX 导入测试 | 纳入 |
| `apps/knowledge/tests/test_document_import.py` | 四格式导入测试 | 纳入 |
| `apps/knowledge/tests/test_knowledge_editor_runtime.py` | 浏览器事件/保存运行时测试 | 纳入 |
| `apps/knowledge/tests/test_manage_article_autosave.py` | autosave/CAS/刷新 | 纳入 |
| `apps/knowledge/tests/test_manage_article_edit_page.py` | 编辑入口状态 | 纳入 |
| `apps/knowledge/tests/test_manage_article_history.py` | 历史富文本 | 纳入 |
| `apps/knowledge/tests/test_richtext_display_styles.py` | 展示样式 | 纳入 |
| `apps/knowledge/tests/test_richtext_import.py` | Markdown/TXT/PDF 结构测试 | 纳入 |
| `apps/knowledge/tests/test_richtext_render.py` | 安全渲染测试 | 纳入 |
| `apps/knowledge/tests/test_richtext_service.py` | 富文本服务和媒体测试 | 纳入；需补 P1 测试 |
| `apps/workflow/urls.py` | 审核预览路由 | 纳入，已测 |
| `apps/workflow/views.py` | 审核富文本/媒体预览 | 纳入，已测 |
| `apps/workflow/services.py` | 批准/驳回后继草稿的媒体复制和正文引用重映射 | 纳入，P1 专项已测 |
| `apps/workflow/tests/test_approve_publish_service.py` | 批准后继草稿媒体映射与回滚测试 | 纳入，P1 专项已测 |
| `apps/workflow/tests/test_reject_service.py` | 驳回后继草稿媒体映射与回滚测试 | 纳入，P1 专项已测 |
| `static/css/opsai.css` | 导入和编辑状态样式 | 纳入 |
| `static/js/knowledge_editor.js` | 保存状态与离页保护 | 纳入，Node 检查 |
| `static/js/richtext_editor_source.js` | Tiptap 源码 | 纳入，运行时测试 |
| `static/js/richtext_editor.js` | 已构建 bundle | 纳入，必须与源码配套 |
| `templates/knowledge/article_detail.html` | 员工富文本展示 | 纳入 |
| `templates/knowledge/manage/create.html` | 导入页面 | 纳入 |
| `templates/knowledge/manage/edit.html` | 编辑器和保存状态 | 纳入 |
| `templates/knowledge/manage/edit_unavailable.html` | 无草稿状态页 | 纳入 |
| `templates/knowledge/manage/history_detail.html` | 历史展示 | 纳入 |
| `templates/knowledge/manage/list.html` | 状态一致的编辑入口 | 纳入 |
| `templates/knowledge/manage/preview.html` | 草稿预览 | 纳入 |
| `templates/workflow/review_detail.html` | 审核预览 | 纳入 |
| `deploy/Caddyfile.multi-import-acceptance` | 18027 Caddy 配置 | 纳入 |
| `deploy/Dockerfile.multi-import-acceptance` | 隔离镜像 | 纳入 |
| `deploy/compose.multi-import-acceptance.yaml` | 18027 隔离编排 | 纳入 |
| `deploy/multi-import-acceptance.env.example` | 无秘密环境变量示例 | 纳入 |
| `package.json` / `package-lock.json` | 固定 Tiptap/esbuild 依赖 | 纳入 |
| `pyproject.toml` | 测试/检查配置 | 纳入 |
| `tasks/CURRENT_TASK.md` / `tasks/TASKS.yaml` | 任务状态与证据 | 纳入 |
| 本报告 | 最终验收证据 | 当前生成，纳入 |

建议暂存必须使用逐文件 `git add -- <path>`，不得使用 `git add .` 或 `git add -A`。本轮 P1 修复、格式检查和 Firefox 复验均已完成；暂存前仍应重新运行 `git status --short`，确保候选数和本表一致。

## 8. 建议提交信息（修复后使用）

```text
feat: 支持多格式知识文档受控导入

更新内容：
- 支持 DOCX、TXT、Markdown 和 PDF 转换为安全结构化富文本并保留受控原文件。
- 补齐富文本编辑、自动保存、审核预览、私有媒体和导入来源审计。
- 修复草稿入口、空结构节点、文字标记协议和后续草稿媒体引用重映射。

验证结果：
- <填写修复后的实际完整测试、Django check、迁移、Ruff、JS 构建和 diff 检查结果>
- <填写 Firefox 复验结果>

影响与回滚：
- 影响知识导入、富文本编辑、私有媒体和审核预览；新增导入来源迁移。
- 回滚前需评估已导入版本和私有媒体关联，不删除数据卷或原始文件。
```

## 9. 结论

**READY_TO_COMMIT**。

P1 代码缺陷、Ruff format 和 KB-000009 v2 的受控数据修复均已完成；本轮实时数据库核验、自动化回归、隔离服务健康检查及负责人 Firefox 最终复验均未发现 P0/P1 阻断。仓库根 `pytest -q` 仍会收集未接入的历史 Wagtail PoC 并报 16 个环境/导入错误，已单独如实记录，不能称为“全仓 pytest 绿色”。
