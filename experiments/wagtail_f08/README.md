# F08A：正文展示格式与转换边界确认

日期：2026-09-15。基线为 `fusion/wagtail-poc`，HEAD `196128e863d664cee8246c54234a62aa1b446fdc`；执行前工作区干净、暂存区为空。

## 结论

首版采用普通文本。F08B 只自动支持经 F07 `opsai.legacy-body/1` 封套和 SHA-256 完整性校验后、payload 类型严格为 `str` 的正文；原字符串及换行原样输出。字符串内已有的标题行、空行、`1.`/`-` 等步骤和列表标记可以作为普通文本保留，但不推断语义层级，也不生成 HTML。

当前源码没有足够的旧正文结构规范。`ArticleVersion.body` 是可为空、默认 `{}` 的 JSONField，注释仅称其为富文本编辑器产生的权威结构化正文；模型没有约束顶层类型、节点字段、节点顺序或标题/段落/步骤/列表/图片/表格 schema。`body_plaintext` 明确是用于检索、差异比较及后续 RAG 的派生文本，不是权威正文，也没有与 body 一致的校验。PRD 只要求结构化正文、步骤和图片等产品能力，没有定义可执行的数据格式。

现有合成证据也不是格式规范：F07 纯函数夹具有嵌套字典和混合数组，数据库导入夹具还使用顶层列表，其他模型/选择器夹具常使用默认空字典。这些值证明 JSON 类型及可逆编码能力，不能证明“段落”“数组”“状态”等任意键具有稳定展示语义。

## 映射与拒绝边界

| 旧字段或解码后结构 | 首版可读表达 | 信息损失 | 不支持时处理 |
| --- | --- | --- | --- |
| F07 正文封套：format=`opsai.legacy-body/1`、payload、sha256 | 先严格调用既有 `decode_body()` 验证格式、字段、重复键和摘要，再处理 payload | 解封本身不损失支持范围内的值 | 非封套、未知版本、损坏 JSON、字段异常或摘要不符，返回明确错误；不能因文本“看起来像 JSON”就解码 |
| payload 为 `str` | 原字符串作为普通文本；保留中文、空格、换行及已有的标题/步骤/列表字符 | 不丢字符；没有结构化标题、列表或链接语义 | F08B 按本轮契约原样保留所有经 F07 支持的字符串字符，不额外清洗或改写；后续表单另行校验 |
| payload 为 `dict`，包括合成 `{"段落": [...]}` 或默认 `{}` | 无可靠自动表达 | 若扁平化会丢键语义、层级、顺序意图及标量类型 | F08B 返回 `unsupported_mapping`；由编辑人员查看原始来源并编辑成明确普通文本，新建草稿后审核 |
| payload 为 `list`，包括合成 `["草稿", {"状态": false}]` | 无可靠自动表达 | 无法判断是段落、步骤、项目列表、富文本节点还是任意数组 | F08B 返回 `unsupported_sequence`；不自动编号、不拼接、不跳过未知元素 |
| payload 为数字、布尔值或 `null` | 不作为正文展示 | 转为字符串会混淆数据类型及业务含义 | 分别返回明确的不支持原因，不用空字符串或 `str(value)` 兜底 |
| 字符串中看似 HTML 的内容 | 按普通文本显示，例如 `<script>` 仍是字符 | HTML 标签没有格式效果 | JSON 层继续正常编码；未来模板必须自动转义或用 textContent，禁止标为可信 HTML |
| 图片、附件或链接节点 | 首版不转换 | 可能丢文件身份、替代文本、权限和引用关系 | 任一结构化节点即拒绝整篇自动转换；附件和图片迁移另行设计，不输出 URL 占位符 |
| 表格、代码块、引用、嵌套列表 | 首版不转换 | 纯文本可能丢单元格关系、语言、引用及层级 | 明确拒绝并要求人工确认；不猜 Markdown 或 HTML |
| `body_plaintext` | 仅可供编辑人员对照 | 它是派生字段，可能已丢结构或过期 | 不作为自动回退，不覆盖权威 body，不因其非空而宣称转换成功 |
| `applicable_scope`、版本说明和旧审核/来源元数据 | 不进入员工正文 | 无正文信息损失，原来源记录仍保留 | 继续留在原业务字段及 F07 来源记录；不拼进正文 |

普通文本足以承载首版人工确认后的标题层级、段落、步骤和列表，例如使用独立标题行、空行、`1.` 和 `-`。它不能证明层级结构、生成目录或提供富文本语义，但无需引入 StreamField、富文本编辑器或前端依赖。结构化能力的正式选型应基于真实旧数据 schema 和产品展示要求另行决定。

## 现有合成正文的前后示例

F07 数据库夹具中的旧正文是：

```json
{
  "嵌套": [
    true,
    1,
    1.0,
    null,
    "引号\"\\与换行\n"
  ]
}
```

该 payload 是字典，F08B 按首版规则必须返回 `unsupported_mapping`，不会自动产出员工正文。下面只是编辑人员核对原始值后可保存的新普通文本草稿示例：

```text
示例数据

- 布尔值：是
- 整数：1
- 小数：1.0
- 空值：未填写
- 文本：引号"\与换行
  （此处保留原文本中的换行）
```

非技术人员可以直接阅读后者，但转换明确损失了原键名“嵌套”、数组结构、标量类型边界和 `null` 的原始含义；“示例数据”“布尔值”“未填写”等文字是人工解释，不能由当前源码可靠推导。原 F07 修订、编码正文和 `ImportedVersionSource.source_data` 必须保留，人工结果作为新草稿由真实编辑账号保存并走现有提交、第三方批准和发布流程。

若要展示无损自动转换的支持例，可将经同一 F07 封套验证后的字符串 payload：

```text
网络无法访问

1. 检查网线和无线网络开关。
2. 重新连接公司网络。
3. 仍未恢复时提交 IT 服务申请。

- 请记录错误时间
- 请勿在工单中填写密码
```

原样作为普通文本输出。标题行、段落、步骤和列表字符仍在，但它们只是文本，不转换为 HTML 节点。

## 审核、读取与追溯边界

F07 已有两个导入修订、编码正文及来源记录保持不变。可读转换只产生候选文本；任何改变内容的结果都必须由编辑阶段追加为新 Wagtail 草稿，由真实提交人提交并由合法第三方批准。转换函数本身不保存、不提交、不批准、不发布。

员工读取继续只返回 F06 已核验的 `live_revision` 快照。读取时不临时解码或转换迁移正文，也不将 `latest_revision`、未审核草稿、旧 Article 字段或 `body_plaintext` 补入响应。普通正文和迁移编码正文的区别来自严格格式封套和校验结果，不来自前缀、花括号或“像 JSON”的内容判断。

可读文本不要求可逆；所有损失必须在转换结果中明确，且原始旧版本、F07 可逆编码与来源映射继续提供追溯。旧审核信息、导入操作人、来源 UUID、时间和内部元数据不进入员工正文。

## F08B 最小范围

F08B 限定为“纯函数转换支持的正文结构，输出可读文本及明确的不支持原因”，建议仅新增 `experiments/wagtail_f08/body_text.py`、纯 unittest、隔离 runner，并更新本 README：

- 入口接受一个字符串形式的迁移编码正文，不接受 ORM 对象、修订或 HTTP 参数。
- 先复用 `decode_body()` 完整验证；只在 payload 的精确类型为 `str` 时返回字段白名单结果，例如 `text`、`source_format`、`losses`（字符串正文应为空列表）。
- 为非封套普通文本、伪造/损坏摘要、未知格式、dict、list、数字、布尔和 null 返回稳定的明确错误码及中文原因；不返回部分正文。
- 不使用 HTML 解析/清洗、Markdown 推断或 `str()`/JSON pretty-print 兜底；输入对象不修改，相同输入输出一致。
- 最小测试覆盖中文、多行、已有标题/步骤/列表字符、引号和反斜杠；JSON 外观的字符串 payload 仍按字面输出；普通正文不误解码；损坏/未知封套及每种不支持 payload 明确失败；输出不含审核或来源元数据。

F08B 不写数据库、不接页面、不读取员工权限、不自动保存或发布，也不引入 StreamField、富文本编辑器或前端依赖。

## 本轮检查

本轮仅对照 AGENTS.md、F07 README、conversion.py、F07 合成夹具、ArticleVersion 的 body/body_plaintext 定义、相关模型测试、PRD 正文要求及 F06 详情白名单读取逻辑进行源码与文档一致性核对。只新增本 README，并执行新文档空白检查；没有运行业务测试、导入 Django、连接数据库或修改既有文件。

最终保持 `fusion/wagtail-poc`，HEAD `196128e863d664cee8246c54234a62aa1b446fdc`，暂存区为空；仅新增未跟踪文件 `experiments/wagtail_f08/README.md`。未读取真实 `.env`，未安装依赖，未操作 Docker、数据库、主 worktree，未暂存、提交或推送。完成后停止，不进入 F08B。


## F08B：迁移编码正文转普通文本（2026-09-15）

已实现纯函数 `body_text.convert_encoded_body_to_plaintext(encoded_body)`。返回不可变 `PlaintextResult(success, text, code, reason)`：成功时 `success=True`、`text` 为原字符串、`code="ok"`；失败时 `success=False`、`text=None`，固定错误码和中文原因，不携带部分正文。

函数直接调用 F07 `decode_body()`，没有复制封套解析或摘要算法。仅捕获其公开 `ConversionError` 并映射为 `invalid_encoded_body`；其他程序错误继续抛出。封套校验只证明数据与该封套一致，不证明来源可信、审核批准或员工读取资格。

| 解码结果或输入错误 | 结果代码 | 行为 |
| --- | --- | --- |
| 精确类型 `str`，包括空字符串 | `ok` | 中文、换行、所有空白、引号、反斜杠、JSON/HTML/script 外观及其他字符原样返回；不递归解析、不清洗或信任为 HTML |
| `dict` | `unsupported_mapping` | 拒绝，不抽取字段 |
| `list` | `unsupported_sequence` | 拒绝，不递归或拼接 |
| `int` / `float` | `unsupported_number` | 拒绝，不调用 `str()` |
| `bool` | `unsupported_boolean` | 拒绝；精确类型判断避免 bool 当成 int |
| `null` | `unsupported_null` | 拒绝，不转换为空字符串 |
| 非封套、损坏 JSON、重复/缺失/额外字段、摘要不符或未知版本 | `invalid_encoded_body` | 使用统一中文原因，不返回解出的任何正文 |

成功文本只是普通 Python 字符串，不是清洗后的 HTML；未来页面必须自动转义或使用 `textContent`。函数不读 `body_plaintext`、ORM、审核或来源元数据，不写数据库、不保存草稿、不提交审核、不发布，也不创建员工读取资格。任何用于正式内容的转换结果仍须作为新草稿保存并走现有审核发布流程。

本轮一次运行17个不重复 unittest 方法，全部通过：8项 F08 专项和复用的9项 F07 正文编码/转换回归。覆盖中文多行、空字符串及前后空白、引号和反斜杠、JSON/HTML/script 字符原样保留、全部支持外 payload 类型拒绝、封套/摘要/版本损坏、确定性与输入不变、真实委托 F07 解码及不掩盖程序错误。runner 的两个测试标签互不重叠，禁止 Django/Wagtail、数据库驱动、真实配置、`.env` 和网络导入或访问；实际输出确认纯标准库、无数据库连接。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/run_plaintext.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f08
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f08
```

本轮新增 `body_text.py`、`test_body_text.py`、`run_plaintext.py`，更新本 README；未修改 F07 或其他既有文件。未运行任何数据库、审核或 HTTP 测试。

最终保持 `fusion/wagtail-poc`，HEAD `196128e863d664cee8246c54234a62aa1b446fdc`，暂存区为空；F08 的四份文件未跟踪，已跟踪文件无差异。未读取真实 `.env`，未操作 Docker、数据库或主 worktree，未安装依赖，未暂存、提交或推送。完成后停止，不自动保存草稿或接入员工页面。


## F08C：普通文本草稿与审核读取联通（2026-09-16）

新增 `test_integration.PlaintextDraftReviewReadTests` 与隔离 runner `run_integration.py`，只组合现有入口，不新增转换按钮、URL、批量命令、模型、迁移、settings 或 App（复用 F07 合成配置 `experiments.wagtail_f07.settings`）。合成调用链为：

`import_article(A, importer)` → `convert_encoded_body_to_plaintext(R1.content["body"])` → 有效编辑账号经现有 Wagtail Snippet 编辑 POST 保存普通文本新草稿 R3 → `submit(C, R3, submitter)` → `approve_review(T1, approver)` → `get_employee_article_detail(employee, A)`。

本次内存库执行中的标识为 C=1、导入 R1/R2、普通文本待审 R3、批准后新草稿 R4、批准任务 T1。数字只是本次执行结果，不构成稳定业务编号。

合成旧版本：夹具旧正式版 `ArticleVersion.body` 的 payload 被改为普通字符串（含中文、空行、`1.`/`-` 标记、引号、反斜杠及一段 JSON 外观文本），旧草稿正文改为另一字符串，派生字段 `body_plaintext` 写成互不相同的文本以证明转换不回退到派生字段。转换按契约显式调用 F08B 纯函数，不因正文“看起来像 JSON”自动判断；字符串内的 JSON 外观片段原样保留为普通文本。

| 阶段 | 正式状态 | 有受众权限员工读取 | 无受众权限员工读取 |
| --- | --- | --- | --- |
| 导入 R1/R2 后 | live=False、无 live_revision、无 TaskState | None | None |
| 显式转换成功后 | 纯计算，数据库完整快照逐行不变 | None | None |
| 编辑账号保存 R3 后 | latest_revision=R3，仍未发布 | None | None |
| 提交 R3 后、批准前 | TaskState/TaskSubmission 绑定 R3；编辑账号与提交人分别被现有服务以“受审修订创建者”“本次审核提交人”拒绝 | None | None |
| 合法第三方批准后 | 任务与工作流 approved，live_revision=R3 | R3 的标题「旧正式版」、摘要「旧摘要」及普通文本正文 | None |
| 再保存 R4 草稿后 | latest_revision=R4，live_revision 仍为 R3 | 仍为 R3 的同一普通文本快照 | None |
| 重复调用 import_article 后 | 返回原 C/R1/R2，内容、修订、任务与来源快照不变 | 仍为 R3 | None |

原来源保留：R1/R2 两条 Revision 的完整 `values()`、两条 `ImportedVersionSource`、以及 `Article`/`ArticleVersion`/`ReviewRecord`/`ArticleAudience` 的 legacy 快照，在保存 R3、提交、批准、保存 R4 及重复导入后均未变化。R1 的 `user` 仍是导入人，R3 的 `user` 是实际执行保存的编辑账号，R3 不在导入修订集合中；重复导入仍返回首次的 `ImportResult`，不覆盖普通文本修订、最新草稿或正式内容。自审、受众与批准证据校验均未调整。

不支持输入：夹具原始字典正文经导入后调用转换，返回 `success=False`、`text=None`、`code="unsupported_mapping"`、原因「不支持自动转换，需要人工确认」。失败即停止：`KnowledgeContent`、`Revision`、`ModelLogEntry`、`ImportedVersionSource`、`TaskState`、`WorkflowState`、`TaskSubmission` 的完整快照逐行不变，Revision 仍为 2 条，`latest_revision` 仍是导入的 R2，live=False，无任何任务或提交记录，有权限与无权限员工均为 None。未创建自动人工回退逻辑。

### 文本边界实际行为（未放宽任何表单规则）

- 纯函数原样返回，包括首尾空白：合成 `"  前置空白与制表\t\n第一行\n\n第二行\n末尾空白 \t\n"` 转换后与输入完全一致。
- 现有 Snippet 表单的 `body` 是 `CharField(required=True, strip=True)`（`TextField` → 表单字段，`AdminAutoHeightTextInput`）。经现有 POST 保存后，修订正文实测为 `'前置空白与制表\t\n第一行\n\n第二行\n末尾空白'`：首尾空白（含空格、制表、换行）被去掉，内部制表、换行与空行原样保留。即“纯函数原样返回”与“表单保存结果”是两个不同环节。
- 空字符串：转换成功且 `text=""`。独立构造同一表单类 `KnowledgeContent.snippet_viewset.get_form_class()` 会拒绝，错误实测为 `['必需字段']`，说明正文非空的表单规则本身存在。
- 但现有草稿保存 POST 走的是 Wagtail 的 `saving_as_draft` 路径：`EditView.is_valid()` 在 `saving_as_draft` 且表单为 `WagtailAdminModelForm` 时调用 `form.defer_required_fields()`（`FieldPanel` 对 `TextField`/`CharField` 会写入 `defer_required_on_fields`），并且 `save_revision(clean=not saving_as_draft)` 以 `clean=False` 追加修订。因此空正文实际仍被保存为新草稿（实测 empty_draft=4、`body=''`）；该草稿未发布，员工与无权限员工均读不到。F04B/F05A 只开放 `edit` 动作，故本实验的每次 POST 都属于该草稿路径。
- F08C-1 已将原 `test_empty_plaintext_currently_passes_review_as_empty_body` 更新为 `test_empty_plaintext_draft_cannot_be_submitted_or_approved`：空正文仍可暂存为草稿，但 `submit()` 会在审核记录写入前拒绝；测试夹具构造的旧有空正文待审任务也会被 `approve_review()` 拒绝，任务、工作流与正式内容保持原状。
- 本轮不渲染 HTML 页面，不宣称完成浏览器展示或脚本注入防护。HTML 外观文本（如 `<script>...</script>`）在纯函数与表单保存中都只是普通字符，未来页面必须自行转义或使用 `textContent`。

### 本轮测试与检查

- `run_integration.py` 一次运行 21 个不重复测试，全部通过：4 个新增 F08C 集成测试、8 个 F08 纯函数测试、9 个 F07 正文编码/转换回归；三个标签互不重叠，没有重复收集。Django 系统检查 0 错误、108 条 SQLite 不支持 `db_comment` 的警告、0 silenced；`makemigrations --check --dry-run` 为 No changes detected；runner 只允许 SQLite `:memory:`，白名单环境与审计钩子未检测到隔离违规。
- 现有 `run_plaintext.py` 另一次运行 17 个测试全部通过（同一批 8+9，在禁止 Django/Wagtail、数据库驱动、真实配置、`.env` 与网络的隔离环境中）。两个 runner 合计覆盖 21 个不重复测试方法，其中 17 个在两种环境各执行一次，不重复计数。
- Ruff：`ruff check` 与 `ruff format --check` 对 `experiments/wagtail_f08` 全部通过（6 个文件 already formatted）；`ast.parse` 语法检查通过；两份新文件无行尾空白、无真实制表符、无超过 100 列的行，行尾一致为 CRLF、以换行结尾且无 BOM。已跟踪文件 `git diff --check` 与 `git diff --cached --check` 均为空。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/run_integration.py
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/run_plaintext.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f08
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f08
```

本轮新增 `test_integration.py`、`run_integration.py`，更新本 README；F08 原有四份文件及 F07 等其他既有文件均未修改，共享的转换、导入、审核、发布与读取代码未改动，因此未重复执行其独立历史套件。

最终保持 `fusion/wagtail-poc`，HEAD `196128e863d664cee8246c54234a62aa1b446fdc`，暂存区为空；`experiments/wagtail_f08/` 下 6 份文件（原 4 份 + 本轮 2 份）全部未跟踪，已跟踪文件无差异。未读取真实 `.env`，未安装依赖，未运行服务器，未操作 Docker、持久数据库或主 worktree，未暂存、提交或推送。

本轮仅完成普通文本的草稿保存、重新审核与员工读取联通证据；未完成转换界面、员工展示页面与 HTML 转义验证，也未验证并发、批量迁移与 PostgreSQL，不能据此执行生产迁移。完成后停止，不自动接转换界面或员工展示页面。


## F08C-1：阻止空正文提交审核及发布（2026-09-16）

共用规则位于 `experiments.wagtail_f05a.body_rules`：正文必须是字符串，且 `body.strip()` 非空；失败稳定抛出 `empty_body` 与中文提示「正文不能为空或仅包含空白，请补充后提交审核。」。规则只判断文本非空，不修改原正文、不填充占位文本、不解码迁移封套，也不做 HTML 清洗或内容质量判断。

- `submit()` 从服务端指定的当前待审 Revision 读取正文，在创建/恢复工作流、创建 TaskState 或 TaskSubmission 之前校验；首次提交与驳回后重提走同一路径。
- `approve_review()` 在状态转换与发布前，从 TaskState 实际绑定的 Revision 读取正文并再次校验，不接收客户端正文。旧有空正文在审任务被拒绝后仍为 in_progress，工作流仍为 in_progress，正式内容及 live_revision 不变。
- Wagtail 草稿暂存仍保持原机制，空正文保存成功；区别仅在于该草稿不能进入审核或获准发布。
- F05A 提交 HTTP 将该预期业务拒绝映射为中文 409；F05B 批准 HTTP 沿用 ApprovalRejected/refusal 映射为中文 409。其他未列入捕获范围的程序异常继续向外抛出。

### F08C-1 测试与检查

- F08 集成 runner：22 tests passed（5 项 F08C 集成、8 项 F08 纯函数、9 项 F07 转换回归）；包含空草稿暂存、空字符串/空格/制表/换行提交拒绝、驳回后空白重提拒绝、正常重提批准、旧有空正文任务批准拒绝，以及真实提交和批准 POST 的中文 409。`makemigrations --check --dry-run` 为 No changes detected；仅使用 SQLite `:memory:`，隔离审计通过。
- F05A 提交/驳回定点回归：11 tests passed；F05B 批准与 HTTP 定点回归：20 tests passed。
- 相关文件 Ruff 静态检查与格式检查通过（10 files already formatted）；9 个 Python 文件的 `ast.parse` 语法检查、10 个相关文件的行尾空白与末尾换行检查、`git diff --check` 及 `git diff --cached --check` 均通过。
- SQLite 报告 108 条既有 `db_comment` 不支持警告，0 个系统检查错误；本轮未新增模型或迁移。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/run_integration.py
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f05a/run.py
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f05b/run.py http
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f05a/body_rules.py experiments/wagtail_f05a/services.py experiments/wagtail_f05a/views.py experiments/wagtail_f05b/services.py experiments/wagtail_f08
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f05a/body_rules.py experiments/wagtail_f05a/services.py experiments/wagtail_f05a/views.py experiments/wagtail_f05b/services.py experiments/wagtail_f08
```

本轮未修改草稿表单、模型、迁移、正式配置、角色或 F08 转换逻辑；未读取真实 `.env`，未安装依赖，未运行服务器，未操作 Docker、持久数据库或主 worktree，未暂存、提交或推送。完成后停止，不进入展示页面开发。


## F08D-1：最小员工普通文本详情页（2026-09-17）

仅在 F08 合成配置注册 `GET /experiments/f08/articles/<article_id>/`。视图在检查请求方法和会话认证后，只调用 `get_employee_article_detail(request.user, article_id)`；成功页面直接使用其返回的冻结正式快照，不复制受众或批准证据判断，不读取最新草稿，不调用正文转换函数，也不回退旧版本或 `body_plaintext`。F08 URL 配置继续包含 F06 原有 JSON 详情路由，其响应结构和缓存行为保持不变。

访问和响应边界：

- 普通有效员工不需要 `is_staff` 或 Wagtail 后台权限；沿用既有 SessionMiddleware、AuthenticationMiddleware 和 AccountStateBackend。
- 未登录或会话账号已停用、禁用、离职时固定返回中文 401，且不会调用详情读取器。
- 读取器返回 `None` 时统一返回中文 404；无受众权限、不存在、未发布及其他读取拒绝不区分原因，不返回标题、摘要或正文。
- GET 以外的方法固定返回 405 与 `Allow: GET`；该只读端点不接受任何写操作。
- F08 专用外层中间件对 `/experiments/f08/articles/` 前缀的 200、401、404、405 响应统一写入 `Cache-Control: private, no-store`。

模板只使用 Django 默认自动转义输出标题、摘要和正文；没有 `safe`、`mark_safe`、关闭自动转义、Markdown、脚本 DOM 写入或 `innerHTML`。正文容器使用 `white-space: pre-wrap` 和 `overflow-wrap: anywhere`，保留普通文本内部换行与空白。HTML、script 和 JSON 外观字符串作为转义后的文字输出，不解码迁移封套，也不推断正文格式。

### F08D-1 测试与检查

- `run_page.py` 一次运行 17 个不重复测试，全部通过：5 个 F08D-1 页面专项和 12 个 F06 详情读取回归。
- 页面专项覆盖合法第三方批准普通文本、后续草稿隔离、普通员工无后台权限、统一 401/404/405、所有响应缓存头、标题/摘要/正文自动转义、正文换行保留、F08 独占页面路由，以及 F06 JSON 接口在 F08 配置下保持原行为。
- Django 系统检查 0 错误、108 条 SQLite 不支持 `db_comment` 的既有警告、0 silenced；`makemigrations --check --dry-run` 为 No changes detected。runner 只允许 SQLite `:memory:`，白名单环境与审计钩子未检测到真实配置、`.env`、持久数据库或网络访问。

完整 PowerShell 复跑：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/run_page.py
.\.venv\Scripts\python.exe -I -m ruff check --no-cache experiments/wagtail_f08
.\.venv\Scripts\python.exe -I -m ruff format --check --no-cache experiments/wagtail_f08
```

本轮新增 F08 视图、路由、合成 settings、缓存中间件、模板、页面测试和隔离 runner，仅更新本 README；未修改 F06 读取/JSON 服务、F08 转换、审核服务、空正文规则、正式模型、迁移、角色或正式配置。未启动浏览器或服务器，不宣称完成浏览器验收；未操作 Docker、持久数据库或主 worktree，未暂存、提交或推送。完成后停止，不自动进入下一阶段。


## F08D-2：员工详情页显示验收（2026-09-17）

新增 `preview_page.py`。脚本沿用 F08D-1 runner 的环境白名单与审计限制，在 SQLite `:memory:` 中复用 F06 合成夹具，准备允许普通员工阅读且已由合法第三方批准发布的普通文本修订，再通过 Django 测试客户端真实请求现有 F08 页面。脚本确认响应为 200、缓存头为 `private, no-store`、脚本外观文本已经转义且正文包含 `white-space: pre-wrap` 后，才把响应 HTML 写入仓库外新建的唯一临时目录；客户端 Cookie 随后清空，输出文件不包含会话标识或真实数据。

本次最终产物是**合成数据的离线页面预览**：

- HTML：`D:\Desktop\OpsAI\opsai-f08d2-preview-unr2t0l0\article-detail.html`
- 桌面截图：`D:\Desktop\OpsAI\opsai-f08d2-preview-unr2t0l0\article-detail-desktop-1440x1000.png`
- 手机宽度截图：`D:\Desktop\OpsAI\opsai-f08d2-preview-unr2t0l0\article-detail-phone-width-390x844.png`

实际使用本机 Microsoft Edge `153.0.4234.32` 无头打开生成的本地 HTML，没有启动 Django 服务器。桌面视口为 1440×1000；手机宽度通过 Edge DevTools 协议精确设置为 390×844，实测 `innerWidth=390`、`scrollWidth=390`、`bodyScrollWidth=390`，主卡片边界为 left=12、right=378、width=366，没有整页横向溢出。

首次手机截图暴露卡片贴边及窄屏安全留白不足。模板只做最小样式修正：统一 `box-sizing: border-box`，为卡片设置响应式宽度，在不超过 600 像素时缩小边距、内边距和标题字号，并允许标题、摘要长文本断行。未修改正文、自动转义、认证、受众、读取或审核逻辑。修正后重新执行 F08D-1 `run_page.py`，17 项全部通过；这是模板变更后的既有回归复跑，不作为 F08D-2 新增认证或权限成绩重复计数。

最终截图实际检查结果：中文标题、摘要和正文清楚可读；段落空行、内部缩进、编号步骤和 Windows 路径得到保留；长连续文本在卡片内换行；`<script>`、`<section>` 和 JSON 外观内容显示为普通文字，没有执行或渲染成标签。HTML 仅包含模板内联 CSS 和系统字体回退，不引用外部字体、图片、样式或脚本。

预览脚本 Ruff 静态检查、Ruff 格式检查、`ast.parse` 语法检查及相关文件空白检查均通过，`git diff --check` 与 `git diff --cached --check` 通过。最终产物只读核验确认 HTML 不含 Cookie、会话、CSRF 或合成登录口令，不含外部资源引用，预览目录没有残留 Edge profile。

生成命令：

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -B -X utf8 experiments/wagtail_f08/preview_page.py
```

本轮仅新增预览脚本、更新本 README，并按实际手机显示问题最小调整 `article_detail.html`；未新增业务功能、模型、迁移、列表、搜索或部署配置。未读取真实 `.env`，未连接持久数据库，未启动服务器，未操作 Docker 或主 worktree，未安装依赖，未暂存、提交或推送。完成后停止，不进入列表、搜索或正式部署。
