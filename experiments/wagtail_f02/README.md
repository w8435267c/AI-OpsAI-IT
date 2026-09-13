# F02：隔离环境与依赖兼容性实际报告

日期：2026-09-11。结论：**F02 环境兼容性验证通过**，无遗留阻塞。

**本轮未验证业务模型、accounts.User 集成、审核、内容受众、PostgreSQL 或数据库迁移。**

## 基线与携带文件

| 项目 | 实际结果 |
| --- | --- |
| 主仓库 | `D:\Desktop\OpsAI\AI-OpsAI-IT`，分支 `main` |
| 融合 worktree | `D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`，分支 `fusion/wagtail-poc` |
| 两侧完整 HEAD | `d59c87c660807d80e78727da3c25222c98e606dd` |
| 初始检查 | 融合路径、分支、worktree 均不存在，已从指定 HEAD 新建；主仓库只有两份已知 F01 文档变更，暂存区为空 |
| 文档携带 | 目标 AGENTS.md 原为同一提交的原始文件，确认后用授权携带的 F01 文档替换；ADR 原不存在。仅复制这两份文件 |
| 最终主仓库 | 仍只有 AGENTS.md 修改及 ADR-0002 未跟踪；内容哈希与初始值相同，未暂存、提交或推送 |

两侧对应文档 SHA-256 一致：

- `AGENTS.md`：`2FBF88246852127D4FB45DBAE0612F71A78CBF8A57262C1311523C1C1C42827E`
- `docs/07-ADR/0002-Wagtail融合基线与最小设计.md`：`1284084A549700E308D3EF597C707F233D1AF8F79DD6466D2ADCA7BE06DA688D`

已读取实际 AGENTS.md 和 ADR-0002。本轮用户明确调整其 F02 建议：采用上述路径/分支，实验文件统一放在本目录，使用默认 `auth.User`，不加载业务 App；这些具体授权优先于 F01 的建议，原文完整携带，不改写为已完成业务集成。

## 解释器与安装

原解释器：`D:\Desktop\OpsAI\AI-OpsAI-IT\.venv\Scripts\python.exe`。
新解释器：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc\.venv\Scripts\python.exe`。
新环境由已核验的 `D:\ruan_jian_an_zhuang\python-3.13.13-amd64\python.exe` 创建，`include-system-site-packages = false`。创建前 D 盘可用空间约 72.7 GiB，解释器为 64 位。

| 组件 | 原环境（只读元数据） | 融合环境（实际检查） |
| --- | --- | --- |
| Python | 3.13.13 / 64 位 | 3.13.13 / 同一基础解释器 |
| Django | 5.2.17 | 5.2.17，导入通过 |
| Wagtail | 未安装 | 7.4.3，导入通过 |
| psycopg | 3.3.5 | 3.3.5，含 psycopg-binary，导入通过 |
| python-dotenv | 1.2.3 | 1.2.3，仅核对安装元数据；验证进程禁止导入 |
| Ruff | 0.16.5 | 0.16.5 |

从官方 `https://pypi.org/simple` 下载正式 wheel，未使用 editable 安装、上游 testing/docs extras 或本地源码复制。安装子进程使用环境白名单和 `PIP_CONFIG_FILE=NUL`，不继承私有索引或代理设置，不修改全局配置；无下载重试或依赖冲突。完整 38 项安装版本（含 pip/Ruff）见 `requirements.resolved.txt`，它是实际版本快照，不是带制品哈希的供应链锁文件。Pillow 12.3.0、pillow-heif 1.7.0、Willow 1.12.0 的 Windows 轮子安装及导入通过，未验证图像业务。

## 实际验证结果与限制

| 检查 | 结果 |
| --- | --- |
| 固定依赖安装 | 成功，退出码 0，Django 保持原补丁版本 |
| pip check | `No broken requirements found.`，退出码 0 |
| 导入与来源 | Django、Wagtail、psycopg/binary、Pillow、pillow-heif、Willow 均来自融合 .venv |
| django.setup() | 独立配置下成功 |
| Django system check | `System check identified no issues (0 silenced).`；使用 `fail_level="WARNING"`，无错误或警告，未设置屏蔽项 |
| Ruff 静态与格式检查 | 3 份 Python 文件通过 |
| py_compile | 3 份 Python 文件通过 |
| Git 空白与文件范围 | `git diff --check` 及全部新增文件的 no-index 空白检查通过；未暂存 |

首次执行 `python -I experiments/wagtail_f02/verify.py` 在 setup 期间失败：自建审计拦截器禁止了 modelsearch 的 `sqlite3.connect(":memory:")` FTS5 探测，报“禁止网络或数据库连接”。读取已安装依赖的探测代码后，仅放行内存 SQLite，保留文件数据库及网络拦截；同时显式使用 UTF-8 修复终端中文输出。修正后实测通过。该失败不是依赖冲突或 PostgreSQL 故障。

验证进程只将实验目录加入模块搜索路径，不加入业务根目录；父进程以环境白名单重启子进程，显式指定独立 settings，不继承 DJANGO_SETTINGS_MODULE、POSTGRES_*、PYTHONPATH 或业务凭据。导入哨兵拒绝 config、apps、dotenv；文件审计拒绝任何 .env/.env.* 打开；网络连接/DNS 审计与 Django 数据库连接拦截同时启用。最终无被拦截的违规操作，未加载项目配置。记录到 2 次 modelsearch 临时内存 SQLite 探测；该库在探测后关闭连接，仅检查 FTS5，不执行 Django 迁移，也不验证搜索业务。

配置使用 SQLite `:memory:`、默认 auth.User、内存邮件/缓存/文件存储、DummyBackend 任务后端。Wagtail App 注册只为系统检查；URL 列表为空，不挂载后台、员工页面或启动 HTTP。未运行 migrate、makemigrations、collectstatic、现有业务测试、Wagtail 全量测试或部署检查。本次常规 system check 不证明生产配置安全或后台可用。

沙箱身份读取新 worktree 的 Git 信息曾遇到 dubious ownership；随后在创建它的已授权执行身份下核验，未修改 safe.directory 或其他 Git 配置。

## 本轮文件与未提交状态

本目录新增 6 份文件：

- `requirements.txt`：直接依赖与固定版本，Ruff 仅用于静态检查。
- `requirements.resolved.txt`：实际安装的完整版本记录。
- `f02_settings.py`：独立配置。
- `f02_urls.py`：空路由。
- `verify.py`：环境白名单、隔离拦截、版本/导入/setup/system check 入口。
- `README.md`：本报告及复跑命令。

融合 worktree 另有携带的 AGENTS.md 修改及未跟踪 ADR-0002。现有 .gitignore 已覆盖 .venv、__pycache__、.ruff_cache，无需修改；环境和缓存未纳入 Git。两侧暂存区均为空。主工作目录文件和原虚拟环境未修改；仅按授权新增分支/worktree 的 Git 管理元数据。本轮未修改上游源码、操作 Docker 或开发数据卷。

## PowerShell 复跑命令

使用现有融合环境，无需重建；不通过原 manage.py 或业务 test settings 启动。

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m pip check
```

```powershell
& '.\.venv\Scripts\python.exe' -I -X utf8 experiments/wagtail_f02/verify.py
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m ruff check experiments/wagtail_f02
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m ruff format --check experiments/wagtail_f02
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m py_compile experiments/wagtail_f02/f02_settings.py experiments/wagtail_f02/f02_urls.py experiments/wagtail_f02/verify.py
```

```powershell
git diff --check
```

只有需要补装时才运行下面命令；复用现有环境，使用完整版本约束，保持官方来源及配置隔离：

```powershell
& '.\.venv\Scripts\python.exe' -I -X utf8 -c "import os,subprocess,sys; env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','PATH'}}; env['PIP_CONFIG_FILE']=os.devnull; sys.exit(subprocess.call([sys.executable,'-I','-m','pip','install','--index-url','https://pypi.org/simple','--disable-pip-version-check','--no-input','--no-cache-dir','--retries','2','--timeout','30','-r','experiments/wagtail_f02/requirements.txt','-c','experiments/wagtail_f02/requirements.resolved.txt'],env=env))"
```

## F03 前置事项（仅记录，未执行）

- 另行限定接入范围和隔离配置，将默认用户切换为 accounts.User 后验证字段、依赖与账号状态门槛，不能从本次结果推断成功。
- 明确 Wagtail 后台 URL 与会话准入、非 staff 访问策略，关闭用户/组提权旁路。
- 将 Wagtail 权限纳入集中角色定义，验证 sync_system_roles 的 permissions.set 不会丢失必要权限；继续分离系统角色和内容受众。
- 保留现有模拟登录安全约束；审核组自审、直接发布和历史恢复等问题按 ADR 后续专项验证，不因框架可启动而默认安全。
- 若后续需要迁移或持久数据库，另行授权并建立专用实例/资源，禁止使用开发数据卷；旧历史表、业务读取及受众契约继续保留。

完成 F02 后停止，未进入 F03，未创建提交或推送。
