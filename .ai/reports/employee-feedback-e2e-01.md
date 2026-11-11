# EMPLOYEE-RESOLUTION-FEEDBACK-E2E-01 隔离 E2E 验收记录

## 结论

`BLOCKED / NOT DONE`。本次未达到 E2E PASS，未收口为 DONE，未创建功能或元数据收口提交。

## 现场与隔离边界

- 任务：`EMPLOYEE-RESOLUTION-FEEDBACK-E2E-01`
- 执行分支：`fusion/wagtail-poc`
- 任务登记提交：`323eea2122c379149e2cd007db11d3e7c8c1cf7f`
- 任务登记前代码基线：`cc6215c114b469bb06afe2d91bbaa78e42f43981`
- 隔离 Compose 项目：`opsai-feedback-e2e-01`
- 拟用入口：`127.0.0.1:18014`
- 外部隔离配置目录：`D:\Temp\OpsAI-Feedback-E2E-01`
- 未操作受保护资源：`opsai-local-demo-*`、`opsai-task13-e2e-01`、8001、18013、生产数据库或真实员工数据。

## 实际执行与结果

| 阶段 | 实际命令或核验 | 结果 |
| --- | --- | --- |
| 资源预检 | Docker 项目、命名卷、18014 监听端口均不存在/空闲；`docker compose config --quiet` | PASS |
| 隔离镜像构建 | `docker compose -f D:\Temp\OpsAI-Feedback-E2E-01\compose.yaml -p opsai-feedback-e2e-01 build` | BLOCKED |
| 数据库迁移 | 未执行（构建失败后停止） | NOT RUN |
| PostgreSQL 验证 | 未执行（构建失败后停止） | NOT RUN |
| 桌面浏览器 1280x720 | 未执行（服务未启动） | NOT RUN |
| 手机浏览器 390x844 | 未执行（服务未启动） | NOT RUN |
| 反馈持久化 / 服务入口跳转 | 未执行（服务未启动） | NOT RUN |

## 阻塞原因与证据

构建在 Dockerfile 的 `RUN pip install --no-cache-dir .` 阶段失败。Python 构建隔离尝试下载 `setuptools>=77` 时多次连接 `pypi.org` 读取超时，最终无法满足依赖。此为构建依赖源可用性问题，未发现也未修改业务代码。

原始证据位于独立本地目录，未覆盖历史材料：

| 证据 | SHA-256 |
| --- | --- |
| `compose.yaml` | `92DCC50C1E840CC34A646F46EB5668201D19CBC31943BFA85781E364442A7179` |
| `e2e_settings.py` | `FA806F3173A2A5B7BAB90DBC5CA7484B58B49C8FAB330A91381F1D7FFD5D8C31` |
| `build.stdout.log` | `0F48C97B805BDC154EEC483697510A99E5365C0F870B30AEC700F991E8AC441B` |
| `build.stderr.log` | `42A6FA36922083B5588B33EFEA1ABE01BA39C48B533C3D5577B681156D8A0079` |

构建失败后复核结果：`docker compose ps` 为空；本任务标签下没有容器；没有 `opsai-feedback-e2e-01-*` 数据卷。因此未发生隔离数据库写入，也没有浏览器证据可供宣称 PASS。

## 后续准入条件

需要项目负责人提供新的明确执行授权，并确认一种受控的构建依赖来源（可访问的可信 Python 包源、经批准的内部镜像源，或已验证的预构建镜像）。获得新授权后必须重新预检资源名称与端口，不能把本次 `BLOCKED` 自动视为可重试许可。

## 2026-11-11 恢复执行记录（追加，不覆盖原 BLOCKED 证据）

### 隔离恢复结果

- 已按追加授权复用本地可信基础镜像 `opsai-task13-e2e-01-web:e2e-01529d2`（镜像 ID：`sha256:1d3e5c272134…`）；运行时为 Python `3.13.15`、非特权 `appuser`，未修改该基础镜像。
- 在仓库外 `D:\Temp\OpsAI-Feedback-E2E-01\Dockerfile.reuse-task13` 创建最小恢复 Dockerfile：仅 `FROM`、复制当前源码和设置所有权；没有 `pip install`。
- 目标镜像 `opsai-feedback-e2e-01-web:323eea2`（`sha256:9b78b1bb9cdf26bdbe7fab08c18f4af0d5dea8246acac29882c7f77f30a97852`）使用 `docker build --network=none --pull=false` 构建成功。构建未访问 PyPI、未下载 `setuptools`、未修改项目 Dockerfile 或依赖锁定文件。
- 已启动独立 Compose 项目 `opsai-feedback-e2e-01`，仅创建其网络、`opsai-feedback-e2e-01-postgres-data`、`opsai-feedback-e2e-01-private-media`、数据库和 Web 容器；Web 只监听 `127.0.0.1:18014`。受保护的 `opsai-local-demo-*` 与 `opsai-task13-e2e-01` 资源未被停止、重建、删除或修改。
- 隔离数据库迁移和 `manage.py check` 均通过，`knowledge.0007_feedbackrecord` 已在隔离数据库应用。

### PostgreSQL 与服务端验收

| 项目 | 实际结果 |
| --- | --- |
| 专项 PostgreSQL 自动化测试 | `apps.knowledge.tests.test_employee_feedback` + `apps.service_desk.tests.test_request_entry`：10/10 PASS |
| 已解决/未解决持久化 | 真实隔离库中恰有 `resolved`、`unresolved` 各一条，均关联 `dev_employee` 和当前已发布版本 |
| 重复同类反馈 | 浏览器重复未解决反馈显示“已收到相同反馈。”；记录数未增加 |
| 未登录、无权、草稿/未发布 | 自动化测试通过；浏览器未登录访问被拒绝，无权及草稿文章均返回“未找到可查看的知识。” |
| CSRF、受众权限、无效/缺失服务入口 | 自动化测试通过 |
| 受控服务入口 | 服务端已验证对可见文章返回 `302 -> http://127.0.0.1:18014/health/live`，目标健康检查返回 `200`；该地址只用于本隔离验收 |

首次使用带受控服务 URL 的临时 `e2e_settings` 运行上述测试时，其中两项“默认未配置服务入口”的测试按预期与该临时配置冲突；随后使用保持 PostgreSQL 隔离数据库而默认服务入口为空的开发设置重跑，最终 10/10 通过。该临时测试数据库已由测试框架销毁，未影响隔离运行库。

### 浏览器验收与当前阻塞

- 已使用真实浏览器完成桌面 `1280×720`：合成员工登录、搜索可见文章、打开详情、提交“已解决”、提交“未解决”、刷新后复核、重复反馈幂等、未登录拒绝、无权文章拒绝。
- 已使用真实浏览器完成手机 `390×844`：反馈按钮和受控服务入口在详情页显示且可操作，未发现明显布局阻塞。
- 初始受控测试 URL 指向不存在的本地测试路径，浏览器点击已实际进入该路径并得到 `404`。随后只修改仓库外临时设置，将受控目标调整为同一隔离服务的 `/health/live`，并仅重启本轮 Web 容器。
- 调整后，浏览器工具对内部服务入口路由 `/service-request/KB-000001/` 返回 `net::ERR_BLOCKED_BY_CLIENT`，因此无法取得“浏览器实际跳转至 200 目标”的最终证据。服务端 302 与目标 200 已独立验证，但不能替代该项浏览器验收。

**当前结论仍为 `BLOCKED / NOT DONE`。** 按任务失败/阻塞停止规则，不更新任务为 DONE，不创建收口 Commit；隔离环境和原始证据保留供负责人核查。

### 恢复证据哈希（SHA-256）

| 证据 | SHA-256 |
| --- | --- |
| `Dockerfile.reuse-task13` | `57497AF60EBFEC023C21CC2542BBA8F1A40B613E5F35BCA000E48804379F22FF` |
| `compose.yaml` | `92DCC50C1E840CC34A646F46EB5668201D19CBC31943BFA85781E364442A7179` |
| `e2e_settings.py`（恢复后的受控测试目标） | `59A537BEE9975E1A297F6DD2F96BCADE052C7A32796D381AEBF7EE483F2AE3F1` |
| `evidence-desktop-detail-before-feedback.png` | `25AD94BB51F370EAFCABC2E4667F215BEBC2AA4D36EC40AFB337DF8D34010E8F` |
| `evidence-desktop-resolved.png` | `31590D90369CB17344940BD7C873485DFCA75D7F2EA6C3160A23AB9879985D4B` |
| `evidence-desktop-unresolved.png` | `B6D571458BEBB466C6CCBB98B2BFBCB166E6E114DBDCCE4787741D7A4754B4F7` |
| `evidence-mobile-feedback-controls.png` | `DDD8778DD73BA04E9DD9C3D0A3E9556C86F333E1A0ED3B9B075F9E2E9B37F64C` |

### 下一步最小恢复条件

负责人需确认可接受的浏览器验收工具或在不改变业务代码的前提下允许采用不会拦截内部 `/service-request/` 路由的隔离浏览器环境。该恢复只需复核已启动的隔离环境中的最终服务入口浏览器跳转；不得重建镜像、重跑已有通过的数据库验证，也不得把本次 BLOCKED 状态自动视为再次执行授权。

## 2026-11-11 人工浏览器补验与最终收口

### 验收方式与证据完整性

本节为 `MANUAL BROWSER E2E`：由项目负责人使用 Chrome 在隔离环境中人工完成登录、打开已发布知识、选择“未解决”、点击 IT 服务申请入口和验证目标页。它不是自动化浏览器测试。

人工证据目录：`D:\Temp\OpsAI-Feedback-E2E-01\evidence\manual\`。

| 文件 | SHA-256 | 核验 |
| --- | --- | --- |
| `01_feedback_article_page.png` | `2BB2987DEF8C9B347CCD5B4D12919406F03F26A55C3A20F7F9C7FF692B1AAC0A` | 与 `SHA256SUMS.txt` 一致；地址栏为 `127.0.0.1:18014/kb/KB-000001/`，页面显示已发布知识的“未解决”按钮和“仍未解决？提交 IT 服务申请”入口 |
| `02_service_redirect_health_live.png` | `3118525121F5D0479F1DE66CC566E4E1B1DB2E63B0AEC04AE71A5A1D48787320` | 与 `SHA256SUMS.txt` 一致；地址栏为 `127.0.0.1:18014/health/live`，页面显示 `{"status": "ok", "service": "opsai-it"}` |

截图文件为有效 PNG，清单格式有效；两项哈希均通过重新计算核验。

### 既有证据复核

- 隔离 PostgreSQL 专项测试：`apps.knowledge.tests.test_employee_feedback` 与 `apps.service_desk.tests.test_request_entry`，10/10 PASS。
- 本次只读复核隔离数据库：`KB-000001` 恰有 `resolved`、`unresolved` 各一条反馈，均由合成员工 `dev_employee` 提交，且二者 `article_version_id` 均等于当前已发布版本 ID。
- 已有浏览器证据覆盖搜索、详情、已解决、未解决、刷新、重复幂等、未登录、无权、草稿拒绝及 390×844 控件显示；本次人工补验补足此前自动化客户端无法提供的最终导航证据。
- 此前 `ERR_BLOCKED_BY_CLIENT`、初始受控测试 URL 404 及其恢复过程均保留为历史记录，不被改写。

### 最终结论

`DONE / PASS`。所有本任务必需的隔离部署、迁移、PostgreSQL、反馈持久化、权限/幂等、桌面/手机浏览器证据及受控服务入口跳转均已有可追溯证据。真实 ITSM、真实钉钉、生产凭据和生产环境未被调用或验收；`/health/live` 仅为本地受控跳转目标，不代表真实 ITSM 已接入。
