# F03B 集中角色权限与同步幂等验证

结论：本任务实际执行 89 项测试全部通过，无阻塞。2026-09-12 完成报告及收尾检查。结果仅适用于融合实验配置与 SQLite 内存数据库，尚未接入正式运行配置。

## 基线与修改范围

- 工作目录：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`；分支 `fusion/wagtail-poc`。
- 完整 HEAD：`d59c87c660807d80e78727da3c25222c98e606dd`。
- 解释器：本 worktree 的 `.venv\Scripts\python.exe`；实际 Python 3.13.13、Django 5.2.17、Wagtail 7.4.3，未改变依赖。
- 修改 `apps/accounts/roles.py`、`apps/accounts/management/commands/sync_system_roles.py`、`apps/accounts/management/commands/create_dev_users.py`。
- 新增本目录 `settings.py`、`default_settings.py`、`default_urls.py`、`run.py`、`test_profiles.py`、`test_access.py`、`test_default.py`、`README.md`。
- F01 AGENTS/ADR-0002、F02 六文件、F03A 六文件，共 14 个文件执行前后 SHA-256 一致。未修改主 worktree、正式配置、原测试、历史迁移或 Wagtail 源码。

## 完整权限差异

原完整集合唯一维护在 roles.py 的 SYSTEM_ROLES；融合配置由原集合加最小增量构造。配置必须显式选择，不根据安装状态自动切换。

| 角色 | default 数量 | wagtail-poc 数量 | 全部新增 | 删除 |
| --- | ---: | ---: | --- | --- |
| 普通员工 | 0 | 0 | 无 | 无 |
| 知识编辑员 | 8 | 9 | wagtailadmin.access_admin | 无 |
| 知识审核员 | 6 | 7 | wagtailadmin.access_admin | 无 |
| 知识库管理员 | 19 | 20 | wagtailadmin.access_admin | 无 |

测试使用原角色测试独立列出的完整预期集合逐项比较，数量仅作辅助断言。没有新增 accounts.change_user、auth.change_group、任何 delete 权限，或 Wagtail 页面、图片、文档、工作流权限。

sync_system_roles 不传参数即 default，融合需显式 `--profile wagtail-poc`。先验证配置档、必要 App 和全部权限；入口权限必须属于 wagtailadmin.admin ContentType。缺失时明确失败，不伪造权限记录。所有受管理角色的更新位于一个 atomic 事务内，精确设置所选集合，不在启动、登录或 Signal 中自动同步。

create_dev_users 原本内调角色同步，因此增加同名参数并显式透传；安全开关、固定身份预检、非 superuser、不可用密码和 staff 定义不变。融合调用必须传该参数；默认调用按原契约恢复原权限，会撤销三个角色的 access_admin。已验证配置切换及既有会话随之失去入口权限。所有命令仅在测试内存数据库调用。

## 隔离和实际结果

复用 F03A 独立配置、URL、账号状态认证后端和环境白名单；额外加载现有 knowledge App，为原角色权限及开发身份业务关联预检提供依赖，没有新增内容模型。

入口使用 -I 和白名单子进程环境，强制选择独立配置；阻止 config/dotenv 导入、.env 读取、网络连接和 DNS 查询。迁移前断言默认数据库及测试数据库均为 SQLite :memory:，审计实际 SQLite 连接，应用已有迁移使用 run_syncdb=False。内存邮件、本地缓存；没有 PostgreSQL、文件数据库、Docker、HTTP 服务或外发通知。

| 本任务实际运行 | 测试数量 | 结果 |
| --- | ---: | --- |
| F03B 融合：集合/同步 13 + 请求 8 | 21 | 全部通过 |
| 默认兼容 2 + 原角色/开发身份 45 | 47 | 全部通过 |
| F03A 既有入口回归 | 21 | 全部通过 |
| 合计，不另计 subTest 组合 | 89 | 全部通过 |

验证内容：

- 完整权限集合与禁止权限、重复同步权限及 Group 主键不变、切回默认恢复原集合。
- 无效配置、缺 App、ContentType、Permission 均失败且无部分更新。第三个角色保存注入异常后，旧组修改和新组创建全部回滚。
- 无关组、用户成员关系、直接权限、密码和账号状态，以及内容 UserGroup/成员关系不变。受管理组手工添加的额外权限按所选集合清除。
- 真实 /cms/login/ POST；访问用户只有角色组授权，没有直接权限。员工被拒，三个授权角色可进入；编辑员、审核员仍非 staff，Django Admin 受保护页面拒绝访问。
- 三个角色登录后变为 inactive、disabled、departed，首页和 account 入口下一请求均拒绝。F03A 回归另覆盖错误密码、退出及异常 superuser 等既有契约。
- 三个角色均不能通过 GET/POST 新增、修改用户或组及其权限；POST 使用有效 CSRF，每次拒绝后核对用户、组、权限与关联数据未变。
- 知识管理员原 view_user/view_group 允许 Wagtail 列表及 Django Admin 只读查看，但写入 POST 被拒；编辑员、审核员不具备该只读权限。
- 默认配置只启用 Django/accounts/knowledge，导入守卫阻止加载任何 Wagtail 模块，原 45 项测试未放宽。Wagtail 包仍实际安装，此证据是“未启用并禁止导入”，不是另建无包环境。

测试运行器实际执行 Django system check（含数据库检查），没有错误。F03B 两个配置各有 108 条现有注释警告：97 条 fields.W163（SQLite 不支持字段注释），11 条 models.W046（不支持表注释）。F03A 为 28 + 5 = 33 条。全部保留、0 silenced，不代表 PostgreSQL 验证通过或失败。

Ruff 静态及格式检查、修改/新增 Python 语法检查、Git 差异与新增文件空白检查通过。日志 validation.log、f03a-regression.log 被现有 *.log 规则忽略；虚拟环境和缓存沿用既有忽略规则，未修改 .gitignore。

## PowerShell 复跑

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f03b/run.py
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f03a/run.py
```

F03B 入口依次运行 fusion/default 两个独立进程，可在末尾加 fusion 或 default 单独复跑；运行器自动执行系统检查。不要使用会导入真实配置链的 manage.py 代替此入口。

```powershell
.\.venv\Scripts\ruff.exe check apps/accounts/roles.py apps/accounts/management/commands/sync_system_roles.py apps/accounts/management/commands/create_dev_users.py experiments/wagtail_f03b
.\.venv\Scripts\ruff.exe format --check apps/accounts/roles.py apps/accounts/management/commands/sync_system_roles.py apps/accounts/management/commands/create_dev_users.py experiments/wagtail_f03b
git diff --check
```

## 最终状态与边界

保留原有 F01/F02/F03A 未提交成果，另有本轮 3 个跟踪文件修改、8 个新增实验文件；暂存区为空。没有提交、推送或进入 F04。未对真实账号或持久数据库执行角色同步。

未验证正式配置、PostgreSQL、并发同步或内容功能；atomic 回滚测试不代表并发安全。后续正式接入仍需单独确认配置档调用链、权限迁移就绪、既有权限数据影响及账号门槛部署。Django Group 与内容受众 UserGroup 继续分开，员工受众 Selector 未改变。

F03B 仅完成后台入口角色权限及同步验证，尚未实现内容编辑、审核、发布或员工受众接入。
