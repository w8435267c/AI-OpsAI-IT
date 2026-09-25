# OpsAI Current Task

## 1. 任务身份

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `9` |
| 任务名称 | 配置 Django Admin 和最小演示数据 |
| 优先级 | `MUST` |
| 当前状态 | `READY` |
| 当前负责人 | `unassigned` |
| 依赖 | 任务 `8`，当前为 `DONE` |
| 任务来源 | `tasks/TASKS.yaml` |
| 选择依据 | 项目负责人在 OPS-H07 明确指定 |

项目负责人已经在 OPS-H07 阶段明确指定任务 9 为下一根唯一接力棒。该决定不是 AI 自动选择，也不表示业务开发已经开始。当前尚未授权实施、尚未指定执行 Agent，因此任务必须继续保持 `READY / unassigned`，不得提前标记为 `ASSIGNED` 或 `IN_PROGRESS`。

## 2. 为什么现在做

任务 8 已完成，正式工程已经具备服务端内容受众过滤、拒绝优先和后台联合校验等基础边界。

在继续开发正式员工首页、分类页和知识详情页之前，需要先建立一个安全、可控的 Django Admin 维护入口，以及一套能够重复生成、不会污染已有数据的最小演示数据。这样后续页面、权限和内容流程才能使用稳定样本进行验证，而不需要依赖临时手工数据或 Wagtail 隔离实验。

## 3. 任务目标

按既有第 9 步规划完善可控的 Django Admin 与可重复的最小演示数据，为后续正式员工页面和内容流程提供安全样本。

本任务不得自行增加新的产品能力，也不得借机决定或实施 Wagtail 正式融合。

## 4. 已知现状

- 任务 `8` 已为 `DONE`，任务 9 的登记依赖已满足。
- 正式 Django 工程在电脑 B 的既有验证证据为：`386 passed`、Django system check 通过、Ruff 检查通过。
- Python 为 3.13.13，项目根目录 `.venv` 已建立，正式项目依赖已安装并通过 `pip check`。
- Docker Desktop、WSL 2、Docker Engine 和 Docker Compose 已就绪。
- 真实 `.env` 尚不存在；未读取、未创建。
- OpsAI PostgreSQL 容器、命名卷和数据库尚未创建或启动，未执行 `migrate`，未访问或修改持久数据。
- Wagtail 仍位于 `experiments/wagtail_*` 隔离 PoC，尚未进入正式根 `pyproject.toml`、正式 `INSTALLED_APPS` 或正式根 URL。
- 正式 Admin 当前注册的账号与组织对象包括 `User`、`Department`、`UserDepartment`、`UserGroup`、`UserGroupMembership`。
- 正式 Admin 当前注册的知识对象包括 `KnowledgeSpace`、`Category`、`Article`、`ArticleAudience`、`ArticleVersion`、`ReviewRecord`。
- `ArticleAdmin` 当前禁止新增文章；正式 KB 编号生成服务尚未实现。
- `ArticleVersion` 对非超级管理员保持只读，`ReviewRecord` 对所有人（包括超级管理员）禁止通过普通 Admin 新增、修改或删除。

任务 9 不能改变上述 Wagtail 正式融合决策，也不能把 PoC 能力描述为正式上线能力。

## 5. 依赖关系

- 直接依赖：任务 `8`——内容受众权限选择器与联合后台边界。
- 当前依赖状态：`DONE`。
- 当前选择状态：项目负责人已选择任务 9 作为唯一接力任务。
- 当前执行状态：尚未授权开始，仍为 `READY`。
- PostgreSQL 不是开始编写和测试任务 9 的默认前置条件；如果验收范围要求真实 PostgreSQL 写入，则必须先取得单独授权。

## 6. 允许修改范围

以下范围只在项目负责人以后明确授权开始任务 9 后才原则上允许修改；当前尚未取得该授权：

- Django Admin 直接实现：
  - `apps/accounts/admin.py`
  - `apps/knowledge/admin.py`
- 仅在现有 Admin 表单与事务校验确有需要时：
  - `apps/accounts/forms.py`
  - `apps/knowledge/forms.py`
  - `apps/knowledge/validation_context.py`
- 最小演示数据生成入口：
  - 优先复用现有 `apps/accounts/management/commands/` 结构；
  - 如果演示数据职责属于 knowledge，可在授权后于 `apps/knowledge/management/commands/` 下新增最小命令包和命令文件；该目录当前尚不存在，不得仅为分层美观创建其他架构层；
  - 若最终采用 fixture 或小型 Service，必须位于对应正式 App 内，并在开始实施前明确具体路径和职责。
- 与任务 9 直接相关的测试：
  - `apps/accounts/tests/`
  - `apps/knowledge/tests/`
  - 只有跨 App 行为确有必要时才使用根 `tests/`。
- 状态文档：只有状态流转或负责人验收明确要求时，才同步更新 `tasks/TASKS.yaml`、`tasks/CURRENT_TASK.md` 和 `docs/PROJECT_STATE.md`。

任何超出以上范围的变更都必须先说明原因并取得项目负责人授权。

## 7. 原则上禁止修改范围

任务 9 原则上禁止修改或接入：

- `experiments/wagtail_*` 及其中的实验模型、路由、Admin、runner 或测试；
- 根 `pyproject.toml` 中的正式 Wagtail 依赖；
- 正式 Wagtail settings、`INSTALLED_APPS` 和正式根 URL；
- 将正式内容模型改成 Wagtail 模型；
- `deploy/`、Docker 基础架构和生产配置；
- 真实 `.env` 及任何真实密钥、密码、Token、Cookie 或数据库凭据；
- 与任务 9 无关的业务 App、页面、搜索、审核发布、附件、钉钉或 IT 服务入口；
- 现有 `migrations/` 文件；
- 未经批准的新 migration；
- 真实数据库数据的批量删除、清空、覆盖或重建；
- `docs/HANDOFF.md`，该文件属于 OPS-H08。

Migration 不是项目永久禁止项，但任务 9 不得自动创建或修改 migration。如果实施中发现确实需要改变数据模型，应立即停止对应实施，说明模型变化、迁移影响和回滚风险，并向项目负责人申请扩大范围。

## 8. 特别保护规则

### 8.1 Admin 与权限保护

- 有权限的管理员只能维护任务规划允许的对象：知识空间 `KnowledgeSpace`、分类 `Category`、用户与组织关系、内容用户组，以及符合现有权限边界的 `ArticleAudience`。
- Admin 必须继续使用服务端权限、账号状态、系统角色、受众规则、deny 优先和事务边界；按钮是否可见不能代替服务端授权。
- Admin 身份、`is_staff`、`is_superuser`、编辑员、审核员、知识库管理员、作者或空间负责人身份，都不能自动获得普通员工内容阅读绕过。
- `User` 和系统操作角色 `Group` 的现有保护不得放宽；非超级管理员保持只读。
- `ArticleVersion` 的受控只读边界不得放宽；`ReviewRecord` 继续只能由正式审核 Service 在事务中创建，普通 Admin 对任何人都不得增改删。
- `Article` 的 `kb_no`、`article_status`、正式/工作版本指针、创建人、更新人和时间字段继续按现有规则保护。
- 正式业务数据不得硬删除；删除能力必须符合项目现有安全规则和模型 `PROTECT` 边界。

### 8.2 最小演示数据

- 第一次执行应创建任务验收所需的最小样本。
- 第二次及以后执行不得重复创建同一业务对象，应得到稳定、可说明的幂等结果。
- 不得先全表删除再重建，不得覆盖或“修正”来源不明的既有人工数据。
- 不得依赖数据库自增 ID、固定主键或某次运行顺序判断业务对象身份。
- 数据量只覆盖后续页面、权限和内容流程所需的最小场景，不批量制造无关假数据。
- 如果已有同名但关键字段不一致的对象，应失败关闭并报告冲突，不得静默覆盖。

### 8.3 KB 编号

演示文章必须遵守当前正式 KB 编号规则：全局唯一、不可变，格式为 `KB-000001`。

正式编号服务尚未实现或尚未获得任务范围授权时，不得通过临时字符串拼接、随机生成、硬编码默认编号、Signal、Admin 直接伪造或跳过模型规则创建文章。遇到该前置能力不足时，停止“演示文章创建”部分并报告；其他已授权且不依赖文章编号的 Admin 或演示数据工作不得被伪装成文章创建完成。

### 8.4 Wagtail 隔离

任务 9 不允许把 `experiments/wagtail_*` 挂入正式 Admin，不允许把 Wagtail 加入正式 `pyproject.toml`、正式 `INSTALLED_APPS` 或正式根 URL，也不允许将正式内容模型替换为 Wagtail 模型。Wagtail 是否以及如何正式融合属于后续专门任务。

### 8.5 PostgreSQL 与 `.env`

当前真实 `.env` 不存在，PostgreSQL 尚未启动。如果任务 9 的正式实施或验收需要真实 PostgreSQL，必须先同时满足：

1. 项目负责人通过安全方式配置 `.env` 或等价受控配置；
2. 项目负责人明确授权启动 Compose/PostgreSQL；
3. 项目负责人明确允许的数据库、表、写入范围和回退方式。

在此之前禁止真实数据库写入、创建容器或卷、启动 PostgreSQL、执行 `migrate`，也不得为“先跑起来”填写假凭据或输出真实配置值。

## 9. 验收标准

- [ ] Django Admin 可以按权限维护任务范围内的空间、分类、用户、组织关系、内容用户组和受众。
- [ ] Admin 不形成服务端权限、账号状态、角色、deny 优先或事务边界的绕过入口。
- [ ] 系统生成字段、稳定身份字段、关键状态字段、版本指针、审核/发布证据和审计字段受到保护。
- [ ] 删除能力符合正式业务数据不硬删除、历史证据保留和现有 `PROTECT` 规则。
- [ ] 最小演示数据可以通过一个明确入口重复生成。
- [ ] 第二次执行不会重复创建相同业务对象。
- [ ] 不会全表重建、覆盖未知数据或依赖固定数据库 ID。
- [ ] 演示数据规模保持最小并能支持后续页面、权限和内容流程验证。
- [ ] 演示文章遵守正式 KB 编号规则。
- [ ] 没有使用临时、随机、默认、Signal 或 Admin 伪造方式绕过编号规则。
- [ ] 编号前置能力不足时，已停止文章样本创建并如实报告，未伪造完成。
- [ ] Wagtail PoC 没有被接入正式 Admin、依赖、settings、URL 或内容模型。
- [ ] 与任务 9 直接相关的自动测试通过。
- [ ] 正式 Django 工程必要回归通过。
- [ ] Django system check 通过。
- [ ] `makemigrations --check --dry-run` 通过且没有意外模型变化。
- [ ] Ruff 静态检查通过。
- [ ] 所有实际使用的数据环境、验证范围和未执行项均已如实记录。

## 10. 验证方式

以下是未来正式实施任务 9 后必须执行的验证类型；当前 H09 只检查接力元数据，不执行任务 9 测试或写入：

1. **相关 Django 自动测试**：覆盖 Admin 查看、新增、修改、删除、只读字段、权限漂移、账号失效、越权请求、受众 deny 优先和事务回滚。
2. **演示数据首次执行**：记录创建对象类别、数量和业务标识，确认仅产生预期最小样本。
3. **演示数据第二次执行**：再次运行同一入口，确认对象数量不重复、关键字段不漂移、未知已有数据不被覆盖。
4. **冲突场景**：准备同业务标识但关键字段不一致的合成数据，确认命令失败关闭并给出可理解原因。
5. **KB 编号场景**：确认所有演示文章经正式授权的编号入口创建；若编号服务仍缺失，确认文章样本创建被停止。
6. **正式回归**：运行正式 Django 工程范围测试，不让根目录无限定 pytest 的 Wagtail PoC 收集边界干扰正式结果。
7. **工程检查**：运行 Django system check、迁移一致性检查和 Ruff 静态检查。

命令必须在仓库根目录使用项目 `.venv` 执行，并以任务开始时的 `AGENTS.md`、`README.md`、`pyproject.toml` 和实际 settings 要求为准。当前已有命令入口为：

```powershell
.\.venv\Scripts\python.exe -m pytest apps tests
.\.venv\Scripts\python.exe manage.py check --settings=config.settings.test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.settings.test
.\.venv\Scripts\ruff.exe check .
```

如果当前测试设置要求合成环境变量，只能在对应测试进程内提供非秘密测试值，不得创建或读取真实 `.env`。演示数据命令名称尚未由实现确定，不得在 CURRENT_TASK 中虚构；实施时应选择一个正式、明确、可重复的入口，并对该入口连续执行两次完成幂等验收。

## 11. 开始任务前必须检查

只有项目负责人明确授权开始任务 9 并指定执行 Agent 后，才可进行以下检查并进入业务实施：

1. 依次读取 `AGENTS.md`、`docs/PROJECT.md`、`docs/PROJECT_STATE.md`、`docs/HANDOFF.md`、`tasks/TASKS.yaml`、`tasks/CURRENT_TASK.md`。
2. 核对实际仓库根目录、当前分支、完整 HEAD 和工作区，保护任何未知修改。
3. 确认 `TASKS.yaml` 与本文件仍同时记录任务 9，且状态、负责人和依赖一致。
4. 确认项目负责人已明确授权“开始任务 9”并指定执行 Agent；仅选择接力任务不等于开工授权。
5. 重新核对 Admin、模型、表单、management command 和相关测试的当前实现，不重复实现已有保护。
6. 明确本轮具体文件清单、演示数据对象、是否包含文章样本，以及 KB 编号前置能力。
7. 如果需要 PostgreSQL 或模型变化，先取得对应专项授权；未获授权时停止该部分。

## 12. 完成后的状态更新

### READY

当前状态。任务 9 已被负责人选为唯一接力任务，但尚未授权实施、尚未分配执行 Agent，不得开始业务修改。

### IN_PROGRESS

只有项目负责人明确授权开始并指定执行 Agent 后，才将 `tasks/TASKS.yaml` 与本文件从 `READY` 同步更新为 `IN_PROGRESS`，并填写真实负责人。不得只改其中一处。

### VERIFY

实施完成并取得实际验证证据后，将两处状态从 `IN_PROGRESS` 同步更新为 `VERIFY`，等待项目负责人验收。不得因“代码写完”直接标记 `DONE`。

### DONE

项目负责人验收通过后，按实际证据同步更新 `tasks/TASKS.yaml`、`tasks/CURRENT_TASK.md` 和 `docs/PROJECT_STATE.md`，并在明确授权下形成范围单一的 Commit、完成双端 Push 和三端 HEAD 核验。必要检查未完成或失败时不得标记 `DONE`。

### BLOCKED

只有存在真实阻断条件、当前无法继续时才能使用。必须同时记录阻塞原因、解除条件、已完成内容和未完成内容；“尚未开始”不等于 `BLOCKED`。

### HANDOFF

发生 Agent、电脑或人员切换且任务仍未完成时，进入 `HANDOFF`，并按 `docs/HANDOFF.md` 的正式模板记录真实现场。当前没有真实 Agent 切换，文件应继续保持“当前无待处理 AI 交接”。

## 13. 当前备注

- 当前唯一接力任务是任务 `9`。
- 当前状态仍为 `READY`，负责人仍为 `unassigned`。
- 项目负责人尚未授权业务实施，任务 9 尚未真正开工。
- OPS-H07 已创建本文件；OPS-H08 已创建 `docs/HANDOFF.md`，当前没有待处理 AI 交接。
- 当前 OPS-H09 只检查和最小修正接力元数据，不 Commit、不 Push，不执行任务 9，不执行 OPS-H10。
