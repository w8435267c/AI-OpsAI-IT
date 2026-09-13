# F03A：现有用户与后台访问门槛验证

日期：2026-09-11。结论：**F03A 专项验证通过，21 个测试全部通过，系统检查无错误、有 33 条 SQLite 注释警告，0 条被屏蔽。**

本轮结果仅适用于实验配置和内存测试数据库，尚未接入正式运行配置；未验证内容编辑、审核、员工受众或 PostgreSQL。

## 实际环境与范围

- 工作目录：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`。
- 分支：`fusion/wagtail-poc`；完整 HEAD：`d59c87c660807d80e78727da3c25222c98e606dd`。
- 解释器：该目录 `.venv\Scripts\python.exe`；实测 Python 3.13.13、Django 5.2.17、Wagtail 7.4.3。未安装或升级依赖。
- 独立配置：`experiments/wagtail_f03a/settings.py`，复用已读取的 F02 无凭据实验配置，不导入 config.settings 或 dotenv。
- 在 F02 必需 App 基础上仅增加 `django.contrib.admin`（对照 /admin/）和 `apps.accounts.apps.AccountsConfig`（现有用户、组织关系及已有迁移）。不需要 core、knowledge 等其他业务 App。
- 实验 URL 仅挂载 `/cms/` 与 `/admin/`，仅使用 Django Client，不启动 HTTP 服务，不改主路由。

## 账号状态适配

`auth.py` 中的 `AccountStateBackend` 继承 Django ModelBackend，仅重写 `user_can_authenticate`：必须同时通过原 is_active 检查，且 account_status 为 active。不修改 User.has_perm、集中角色、dev_* 身份或 Wagtail 源码。

已核对实际安装源码：ModelBackend.authenticate 在正常密码检查后调用该方法；get_user 在每次会话恢复时重新查询用户并调用同一方法。因此禁用、离职或 inactive 后，同一 Client 保留原 cookie 的下一请求会成为匿名请求，后台首页和非首页入口均拒绝，superuser 也不例外。实验配置只启用这一个认证后端，未保留可绕过状态门槛的第二后端。

Wagtail 的 require_admin_access 继续检查 `wagtailadmin.access_admin`；staff 不替代该权限，不为 Wagtail 自动提高 staff。Django Admin 保留原 staff 门槛。正常但无 access_admin 的账号可能完成身份认证，后台访问仍被拒绝并返回可正常显示的登录页，不发生重定向循环。仅有后台入口权限不代表可管理用户/组/权限，也不代表有员工内容阅读权限。

这是“每次请求重新判断账号状态”的方案，不是删除所有会话的方案；恢复正常状态后，仍有效的原会话可能再次可用。永久撤销会话、SSO 和其他认证后端接入不在本轮验证范围内。

## 内存迁移与隔离结果

`run.py` 通过白名单环境和 `-I` 启动子进程，显式指定实验 settings。首次 setup 和迁移前断言 default 与 TEST 均为 SQLite `:memory:`；每次 Django 建连再断言。文件打开审计拒绝 .env/.env.*，导入哨兵拒绝项目 config、dotenv 和除 accounts 外的业务 App，网络审计拒绝外部连接/DNS。邮件、缓存、存储和任务后端沿用 F02 的内存/本地 Dummy 设置。

使用 Django DiscoverRunner/TestCase/Client。为避免默认测试建库流程调用 migrate(run_syncdb=True)，只替换测试库初始化与清理：在断言通过的内存连接执行现有 `migrate(run_syncdb=False)`，保留标准测试发现、系统检查和 TestCase 事务回滚，退出进程即销毁内存数据库。不设置 MIGRATION_MODULES、不生成迁移、不使用 syncdb。

实际应用 accounts.0001/0002、Django auth/admin/contenttypes/sessions、Wagtail 及其 taggit 相关已有迁移。测试通过 MigrationExecutor 确认所有已安装 App 的叶节点无待应用迁移，验证 get_user_model() 就是 apps.accounts.models.User，auth_user 表不存在，UserDepartment 与 Wagtail UserProfile 外键指向现有用户且约束检查通过。Wagtail 自带初始数据仅存在于内存库，不是正式业务数据或正式角色同步。

## 专项测试逐项结果

共 **21 个 test 方法**，包含参数化 subTest 场景；不是只收集测试。全部通过，测试执行耗时 3.876 秒（不含迁移）。所有请求测试开启 CSRF 校验，登录和越权写入使用真实路由及有效 CSRF，避免把 CSRF/404 误当作权限防护。

| 测试方法（test_ 前缀省略） | 覆盖内容 | 结果 |
| --- | --- | --- |
| user_model_is_existing_accounts_user | get_user_model / 表名 | 通过 |
| existing_migrations_and_foreign_keys | 迁移图、无第二用户表、用户外键与约束 | 通过 |
| anonymous_redirects_without_loop | 匿名访问首页及 /cms/account/ | 通过 |
| login_post_accepts_normal_nonstaff | 真实登录 POST、两个后台入口页面成功且 staff 未提升 | 通过 |
| wrong_password_rejected | 错误密码不创建认证会话 | 通过 |
| login_requires_csrf | 无 CSRF 登录 POST 返回 403 | 通过 |
| normal_without_access_cannot_enter | 正常但无后台权限不进入 CMS | 通过 |
| staff_without_access_cannot_enter | staff 可进 Django Admin，但不能进入 CMS | 通过 |
| nonstaff_with_access_cannot_enter_django_admin | CMS 用户不能进入 Django Admin 用户管理页 | 通过 |
| inactive_login_rejected | inactive 登录失败，两个 CMS 入口拒绝 | 通过 |
| disabled_login_rejected | disabled 登录失败，两个 CMS 入口拒绝 | 通过 |
| departed_login_rejected | departed 登录失败，两个 CMS 入口拒绝 | 通过 |
| inactive_existing_session_rejected | 数据库禁用后，同一会话下一请求拒绝 | 通过 |
| disabled_existing_session_rejected | 数据库改为 disabled 后下一请求拒绝 | 通过 |
| departed_existing_session_rejected | 数据库改为 departed 后下一请求拒绝 | 通过 |
| invalid_superuser_login_rejected | superuser 三种非正常状态均无法登录 | 通过 |
| invalid_superuser_session_rejected | 已登录 superuser 三种状态变更均拒绝 | 通过 |
| access_permission_revoked_from_existing_session | 撤销入口权限后首页及非首页拒绝 | 通过 |
| access_only_cannot_manage_users_or_groups_by_url | 用户/组列表、新增、编辑 6 个真实 URL 均拒绝 | 通过 |
| unauthorized_post_cannot_change_user_or_group_permissions | 用户/组新增或编辑 4 类 POST 均拒绝；目标字段、权限、成员关系、数量不变 | 通过 |
| logout_removes_session_and_blocks_access | 真实退出 POST 清除认证会话，后续两个入口拒绝 | 通过 |

状态变更测试另外检查 /admin/ 也跳到登录；拒绝后的登录页正常呈现，无重定向循环。越权 POST 涵盖尝试赋予 superuser、用户直接权限及组权限。所有直接授权均仅用于 f03a_* 合成夹具，未执行 sync_system_roles。

## 系统检查警告与其他检查

Django 测试运行器实际执行数据库相关 system check：0 错误，33 警告，0 屏蔽项。

- `fields.W163`：SQLite 不支持 db_comment，28 个字段。下表逐项列出，均为同一后端限制。
- `models.W046`：SQLite 不支持 db_table_comment，5 张表，分别属于下表五个模型。

| accounts 模型 | fields.W163 对应字段 | 字段数 |
| --- | --- | --- |
| Department | created_at、dingtalk_dept_id、is_active、last_sync_at、name、parent、updated_at | 7 |
| User | account_status、dingtalk_corp_id、dingtalk_union_id、dingtalk_user_id、display_name、employee_no、last_sync_at | 7 |
| UserDepartment | created_at、department、effective_at、expired_at、is_primary、user | 6 |
| UserGroup | created_at、description、is_active、name、updated_at | 5 |
| UserGroupMembership | created_at、user、user_group | 3 |

未忽略或修改模型注释；这些警告不代表 PostgreSQL 通过或失败。没有其他系统检查错误/警告，也没有专项测试失败。首次静态检查发现一处测试数据行超长，已用 Ruff 格式化修复；最终 Ruff check、format --check 和 5 份 Python 文件的 py_compile 均通过。

Git diff --check 与新增文件逐份 no-index 空白检查通过。F01 两份文档和 F02 六份文件共 8 份 SHA-256 与任务开始时一致；另实际复跑 F02 verify.py 成功，仍为 0 问题、0 屏蔽。未重跑完整业务或 Wagtail 测试套件。

## 文件与复跑方式

仅新增本目录 6 份文件：settings.py、urls.py、auth.py、run.py、test_access.py、README.md。现有 .gitignore 已覆盖 Python/Ruff 缓存，无需修改。

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
```

以下命令包括迁移前隔离断言、内存迁移、Django system check 和全部 21 项测试，不要替换为原 manage.py 或正式配置：

```powershell
& '.\.venv\Scripts\python.exe' -I -X utf8 experiments/wagtail_f03a/run.py
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m ruff check experiments/wagtail_f03a
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m ruff format --check experiments/wagtail_f03a
```

```powershell
& '.\.venv\Scripts\python.exe' -I -m py_compile experiments/wagtail_f03a/settings.py experiments/wagtail_f03a/urls.py experiments/wagtail_f03a/auth.py experiments/wagtail_f03a/run.py experiments/wagtail_f03a/test_access.py
```

```powershell
git diff --check
```

## F03B 待处理与最终状态

F03B 需要另行确认哪些集中角色获得 access_admin，保留非 staff 接入并验证 permissions.set 的完整权限集合及同步幂等；核对 Wagtail 初始 Editors/Moderators 组与业务角色命名及权限的关系。不能把本轮夹具直接授权当成角色接入。特别需要审查授予 change_user/change_group 后 Wagtail 管理入口的能力，现有 Django Admin 自定义保护不会自动覆盖 Wagtail 用户/组管理视图。

后续接入其他认证后端或正式配置时必须保留每请求账号状态门槛，继续遵守模拟登录、内容受众与系统角色分离规则。内容模型、作者自审、发布旁路和员工受众仍待各自任务验证，本轮不实现。

最终分支及 HEAD 未变；暂存区为空。原 AGENTS.md 修改、ADR-0002 和 F02 六份未跟踪文件原样保留，加上本目录六份未跟踪文件；没有本轮之外的文件修改。未操作主 worktree、真实 .env、既有用户、开发数据库、Docker 或数据卷，未创建提交或推送。完成后停止，未进入 F03B/F04。
