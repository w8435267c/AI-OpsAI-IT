# OpsAI Current Task

> 本文件登记唯一当前业务开发任务。本轮仅建立未来内网试点的生产部署配置基线；不部署、不访问生产数据、不接入真实钉钉或外部系统。

## 1. 当前任务

| 项目 | 当前值 |
| --- | --- |
| 任务编号 | `PILOT-PRODUCTION-DEPLOYMENT-BASELINE-01` |
| 任务名称 | 内网试点生产部署基线建设 |
| 任务状态 | `DONE / PASS（仅限本地隔离生产部署配置基线）` |
| 任务性质 | `LOCAL CONFIGURATION AND ISOLATED VERIFICATION ONLY` |
| 登记基线 | `cce0afdf702be4417cc96e6111e2d7f13f2bbedf` |
| 目标分支 | `fusion/wagtail-poc` |
| 前置依赖 | `PILOT-LOCAL-LOGIN-MVP-01` 已 `DONE / PASS`，收口提交 `cce0afdf702be4417cc96e6111e2d7f13f2bbedf`。 |
| 当前授权 | 仅允许任务登记、部署配置开发、离线/隔离验证、验收报告和本地提交；不得真实部署、操作现有容器/数据卷、生产数据、真实钉钉、Push 或 Merge。 |

## 2. 本轮实施范围与验收

- 仓库内允许修改仅为 `tasks/CURRENT_TASK.md`、`tasks/TASKS.yaml`、`deploy/Dockerfile.production`、`deploy/compose.pilot.yaml`、`deploy/Caddyfile`、`deploy/pilot.env.example`、`config/settings/production.py`、`tests/test_production_deployment_baseline.py`、`docs/06-Process/PILOT-PRODUCTION-DEPLOYMENT-BASELINE-01-SOP.md` 与 `.ai/reports/pilot-production-deployment-baseline-01.md`；需要扩展文件范围时必须停止。
- 必须使用 Gunicorn/WSGI、Caddy、内部 PostgreSQL 网络、独立持久卷、`collectstatic` 与受控环境变量；不得使用 `runserver`、源码 bind mount、公开媒体或宿主机数据库端口。
- 生产设置必须失败关闭、`DEBUG=False`、严格 `ALLOWED_HOSTS`、关闭 `/dev/login/`、保留现有认证与知识受众权限，并仅信任受控反向代理。
- 补充授权：`pyproject.toml` 已纳入本任务，Gunicorn 仅作为 Linux 生产镜像运行时依赖声明；不得安装到 Windows `.venv` 充当生产验证。
- 已解除的构建阻塞：原始构建因 Docker 内 PyPI `setuptools>=77` 读取超时失败；改用经 SHA-256 核验的仓库外 wheelhouse、`--network none` 和既有 Linux 应用基础镜像后，Gunicorn 生产镜像构建成功。
- 历史阻塞已保留：此前拉取 `caddy:2.10.2-alpine` 时 Docker Desktop HTTPS 代理不可达，退出码为 1；2026-11-12 已使用核验后的本地官方镜像完成 Caddy、HTTPS、反向代理、静态文件和私有媒体隔离验收。
- 最终验收：TLS 1.3、HTTP→HTTPS、`/health/live`、`/health/ready`、静态文件、私有媒体拒绝、生产 `/dev/login/` 禁用、端口隔离、失败关闭与相关回归均已通过。结果仅适用于合成域名、临时证书和隔离数据库，不代表真实内网部署完成。
- 功能提交：`3b504ab85c48b8b1ceb617f4b9fe9f10f63d8efc`；本文件及任务池的完成状态将由独立收口提交保存。

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
