# OpsAI 跨电脑项目交接检查点（2026-09-18）

本文档用于电脑 A 到电脑 B 的一次性设备切换。它不是正式的 `docs/HANDOFF.md`，不替代后续 OPS-H08，也不授权提前开始 OPS-H04 或其他业务开发。

## 1. 项目身份

| 项目项 | 当前信息 |
| --- | --- |
| 项目 | OpsAI-IT 故障问答知识库 |
| 仓库 | `AI-OpsAI-IT-wagtail-poc` |
| 当前开发阶段 | AI 项目接力第一阶段 |
| 当前业务开发阶段 | Django / Wagtail 隔离融合验证 |

## 2. 当前 Git 状态

以下状态取自 OPS-H03 提交完成后、创建本报告前的现场检查：

| Git 项 | 现场值 |
| --- | --- |
| 当前分支 | `fusion/wagtail-poc` |
| 当前完整 HEAD | `05b5250660b3925ca9776ae89ffa953b19e326c2` |
| 最近 Commit | `05b5250 docs(ai-handoff): add OpsAI project overview` |
| 工作区状态 | 干净 |

最终交接 HEAD 是“包含本报告的最新提交”，提交标题应为 `docs(ai-handoff): record cross-device handoff checkpoint`。提交无法在自身内容中预先记录自己的最终哈希；电脑 B 可在仓库根目录执行以下命令解析该提交，并确认它同时是当前 HEAD：

```powershell
$handoffCommit = git log -1 --format=%H -- .ai/reports/device-handoff-2026-09-18.md
$currentHead = git rev-parse HEAD
$handoffCommit
$currentHead
```

本轮最终执行报告还会记录该完整哈希及 GitHub、Gitee 的实时分支哈希。

## 3. 第一阶段当前进度

```text
OPS-H01：DONE
OPS-H02：DONE
OPS-H03：DONE
OPS-H04：NEXT
OPS-H05：未开始
OPS-H06：未开始
OPS-H07：未开始
OPS-H08：未开始
OPS-H09：未开始
OPS-H10：未开始
```

明天电脑 B 应从 OPS-H04 开始，禁止重复执行 OPS-H01、OPS-H02 或 OPS-H03。

## 4. 已建立的 AI 接力文件

现场确认以下文件实际存在：

```text
AGENTS.md
docs/PROJECT.md

tasks/completed/.gitkeep
tasks/blocked/.gitkeep

.ai/runs/.gitkeep
.ai/reports/.gitkeep

outputs/.gitkeep
```

以下后续文件尚未创建，本次不得提前创建：

```text
docs/PROJECT_STATE.md
tasks/TASKS.yaml
tasks/CURRENT_TASK.md
docs/HANDOFF.md
```

## 5. 当前业务开发基线

- 当前开发分支：`fusion/wagtail-poc`。
- F08D-1 已完成。
- 员工正式知识详情的隔离实验能力已经形成；这表示实验链路已有证据，不表示正式生产能力已经上线。
- Wagtail 当前仍是隔离融合 PoC。
- 尚未切换正式 settings、正式 URL 或生产数据库。
- 不得把 SQLite 内存测试、实验页面或历史验证结果描述为 PostgreSQL、持久数据库或生产验证。

## 6. Git 无法自动带走的本地状态

### 6.1 `.env`

| 检查项 | 结果 |
| --- | --- |
| 是否存在 | 是 |
| Git 跟踪 | 否 |
| Git ignore | 是 |
| 电脑 B 是否可能需要重新准备 | 是；仅在后续运行项目或访问外部集成时需要，由负责人安全单独配置 |

本次只检查存在性、Git 跟踪和 ignore 状态，没有读取或输出 `.env` 正文。

### 6.2 `.venv`

| 检查项 | 结果 |
| --- | --- |
| 是否存在 | 是 |
| Git 跟踪 | 否 |
| 是否需要复制 | 否 |

`.venv` 不需要通过 Git 或复制方式带到电脑 B，建议根据项目依赖重新创建。

### 6.3 PostgreSQL / Docker Volume

- 仓库的 `deploy/compose.yaml` 声明 PostgreSQL 17 和 `postgres_data` 持久卷，Compose 项目名为 `opsai-it`。
- 电脑 A 的 Docker WSL 数据目录 `D:\DockerData\wsl` 存在。
- 盘点时 Docker Engine 未运行，`docker volume ls` 无法连接，因此没有把具体 named volume 的当前存在状态写成已实时验证。
- 仓库内没有发现 `.sqlite`、`.sqlite3` 或 `.db` 文件；自动测试使用的 SQLite `:memory:` 不产生需要迁移的数据库文件。
- 当前继续 AI 接力阶段的 OPS-H04 不需要复制电脑 A 的本机数据库状态。OPS-H04 的正式任务说明仍应在开始时重新核对；在未取得单独授权前，不启动数据库、迁移、dump、export 或 volume 操作。

### 6.4 其他本地状态

| 类别 | 现场盘点 | 交接处理 |
| --- | --- | --- |
| 环境文件 | `.env` 存在且已忽略 | 不进 Git；按需安全重建 |
| 虚拟环境 | `.venv/` 存在且已忽略 | 不复制；在电脑 B 重建 |
| 缓存 | `.ruff_cache/` 和多个 `__pycache__/` 存在且已忽略 | 无需迁移 |
| 数据库 | 仓库内无本地数据库文件；Docker 卷实例未实时确认 | OPS-H04 无需迁移 |
| 日志 | 多个 Wagtail 实验目录存在已忽略的验证日志 | 无需迁移 |
| IDE 文件 | 未发现 `.idea/`、`.vscode/` 或 `.vs/` | 无需迁移 |
| 未跟踪文件 | 创建本报告前无未跟踪文件 | 仅本报告将作为本轮新增文件提交 |
| 用户级 Git 配置 | 电脑 A 存在身份、换行、编码、代理和 Gitee 凭据提供器等用户级配置项 | 配置值未读取且不会进入 Git；电脑 B 按自身环境配置 |
| 用户级 Git ignore | Git 提示电脑 A 的用户级 ignore 文件不可访问 | 不影响本仓库本轮状态判断；电脑 B 不应依赖该文件 |

## 7. 电脑 B 最少需要什么

### 7.1 必须通过 Git 获取

- 完整项目代码和提交历史。
- `AGENTS.md`。
- `docs/PROJECT.md`。
- `.ai/reports/device-handoff-2026-09-18.md`。
- 当前分支 `fusion/wagtail-poc`。

### 7.2 需要重新创建

- Python 3.13 环境。
- 仓库根目录的 `.venv` 和项目依赖；依赖入口为 `pyproject.toml`，不得全局安装项目依赖。
- 后续需要运行正式 Django / PostgreSQL 开发环境时，再按 `README.md` 和 `deploy/compose.yaml` 准备 Docker Desktop、WSL 2、镜像与本机数据库环境。

OPS-H04 为下一项 AI 接力任务，不要求先恢复上述运行环境或本机持久数据库。

### 7.3 可能需要负责人安全单独提供

- `.env`。
- API 凭据、Token 或其他真实密钥。
- 钉钉应用配置和凭据。
- 后续任务明确依赖但不应进入 Git 的其他本机配置。

任何真实值都不得写入本报告、聊天日志或 Git。

### 7.4 当前不需要迁移

- `.ruff_cache/`、`__pycache__/` 等缓存。
- 实验验证日志。
- SQLite `:memory:` 测试状态。
- 电脑 A 的旧 `.venv`。
- IDE 本地设置。
- 用户级 Git 配置值和凭据提供器状态。
- 电脑 A 的 PostgreSQL / Docker volume；OPS-H04 不依赖其数据。

# 电脑 B 恢复步骤

## Step 1：取得仓库

从已完成同步的 GitHub 或 Gitee 获取项目。项目目录由负责人按电脑 B 的实际磁盘和目录规划决定，不要求与电脑 A 相同。

如果电脑 B 已有该仓库和未提交工作，先执行 `git status` 并保护现有工作，不得盲目覆盖或清理。

## Step 2：切换分支

已有本地分支时执行：

```powershell
git checkout fusion/wagtail-poc
```

第一次获取远端分支时，先查看远端分支和实际远程名，再建立本地跟踪分支。例如 GitHub 远程名为 `origin` 且本地分支尚不存在时：

```powershell
git branch --remotes
git checkout --track origin/fusion/wagtail-poc
```

不要执行会覆盖未提交工作的 reset、clean、强制切换或强制拉取命令。

## Step 3：验证代码版本

```powershell
git status
git branch --show-current
git rev-parse HEAD
git log --oneline -10
$handoffCommit = git log -1 --format=%H -- .ai/reports/device-handoff-2026-09-18.md
$handoffCommit
```

必须确认：

- 当前分支为 `fusion/wagtail-poc`；
- 工作区没有意外修改；
- 电脑 B 的 `git rev-parse HEAD` 等于 `$handoffCommit`；
- 该提交标题为 `docs(ai-handoff): record cross-device handoff checkpoint`；
- 该提交之前紧邻 OPS-H03 提交 `05b5250660b3925ca9776ae89ffa953b19e326c2`。

## Step 4：新 Agent 开工先读

当前第一阶段尚未全部完成。电脑 B 的 Codex、Qoder 或 Claude 至少先完整读取：

```text
AGENTS.md
docs/PROJECT.md
.ai/reports/device-handoff-2026-09-18.md
```

不得依赖电脑 A 的聊天记录恢复项目事实。

## Step 5：环境恢复

- Python：使用 Python 3.13。
- 虚拟环境：在电脑 B 的仓库根目录重新创建 `.venv`，不要复制电脑 A 的旧虚拟环境。
- 项目依赖：以 `pyproject.toml` 和对应任务的实验 README 为入口；正式依赖与 Wagtail 隔离实验依赖需要继续区分。
- Docker：需要运行开发环境时，先按 `README.md` 检查 Docker Desktop 与 WSL 2，再使用 `deploy/compose.yaml`；不要为 OPS-H04 提前启动。
- PostgreSQL：需要数据库任务时再由任务范围决定迁移、初始化和数据准备；不要把电脑 A 的本地 volume 当作 Git 交接前提。

本次交接只记录恢复入口，不在电脑 B 安装或初始化环境。

## Step 6：敏感配置

`.env` 和真实密钥不在 Git 中。如果电脑 B 后续任务需要，由项目负责人通过安全方式单独配置；不得把真实值写入仓库、普通日志或聊天记录。

## Step 7：继续任务

```text
下一任务：OPS-H04
```

```text
不得重复 OPS-H01
不得重复 OPS-H02
不得重复 OPS-H03
```

开始 OPS-H04 前重新读取其正式任务说明并确认范围。本交接任务不得直接执行 OPS-H04。
