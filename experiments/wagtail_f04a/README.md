# F04A：最小内容模型与版本隔离验证

日期：2026-09-12。结论：**候选一对一 Snippet 路线可继续**，本轮仅验证其模型及 Revision/DraftState 基础机制，未注册 Snippet 或内容编辑后台。17 项专项测试通过，无阻塞。

## 实际环境

- 目录：`D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc`。
- 分支：`fusion/wagtail-poc`；HEAD：`d59c87c660807d80e78727da3c25222c98e606dd`。
- 解释器：该目录 `.venv\Scripts\python.exe`；实测 Python 3.13.13、Django 5.2.17、Wagtail 7.4.3，未安装或升级依赖。
- 独立 settings.py 复用 F03B 配置及 F03A 账号认证后端，仅增加 fusion_f04a App。未修改共享实验支持代码，不重复执行 F03 套件。

## 模型与源码核对

KnowledgeContent 继承顺序为 DraftStateMixin、RevisionMixin、models.Model。内部 BigAutoField 主键与 Article 的 UUID/KB 编号分开，符合 ADR-0002 的独立内部主键方向；没有把 Article UUID 替换为 Wagtail ID。

| 字段/关联 | 本轮设计 |
| --- | --- |
| id | 稳定的内部 BigAutoField 主键 |
| article | OneToOneField，PROTECT，editable=False，反向名 f04a_content |
| title / summary / body | 中文名称；普通字符/文本字段，不使用 StreamField |
| live | 显式默认 False，新建对象是草稿 |
| latest_revision / live_revision | 继承 Wagtail 版本指针，分别表示最新和正式修订 |
| 其他继承字段 | has_unpublished_changes、发布时间、go_live_at、expire_at、expired；仅因 DraftStateMixin 自带而存在，未实现或验证定时发布 |

读取了实际安装包 wagtail/models/draft_state.py、revisions.py 和 actions/publish_revision.py：上游 live 默认 True，必须覆盖默认值；with_content_json 保留 pk，但会从 JSON 恢复 Article 关联。因此模型在实例保存、修订保存和反序列化时验证稳定身份，遇到伪造关联或 pk 拒绝，不在测试里手动改回关联。RevisionMixin 自带 GenericRelation，无需重复添加修订关联。

本轮仅声明实验 publish_knowledgecontent 权限，由迁移后的标准权限创建机制生成；仅合成测试发布者直接持有。SYSTEM_ROLES 及 F03B 同步命令完全未改。publish_for_test 强制传入数据库中存在且状态正常的用户，调用 revision.publish(user=user)，沿用 Wagtail ModelPermissionPolicy 的 publish 权限检查，不使用 skip_permission_checks。上游 user=None 的调用可不检查权限，因此本入口主动拒绝缺少发布者。

## 实际版本行为

- 新建对象 live=False、无 live_revision，read_live 返回 None。
- save_revision 追加草稿，只更新最新修订指针/未发布变化标志；V1 发布后保存 V2 草稿，数据库正式字段和 read_live 均仍为 V1。
- read_live 重新查询对象，只取 live_revision，并核对 content_type、base_content_type、object_id 及 JSON 身份。不从 latest_revision 读取正式正文；发现非法归属抛错，不返回正文。
- 显式发布 V2 后正式内容切换。restore_draft 将 V1 内容追加为新修订，保持正式 V2；再次显式发布恢复稿后才切换回 V1 内容。
- KnowledgeContent 主键和 Article 关联不变；恢复未删除重建对象，历史修订行内容及时间等字段未改写。受支持修订调用拒绝 overwrite_revision 参数。
- Article.title、两个旧版本指针及其他全部字段，以及已有 ArticleVersion、ReviewRecord 保持逐行一致。夹具包含非空正式/工作版本指针、两条旧版本和一条审核记录，非仅验证空表。

## 保护能力与事务边界

数据库的一对一唯一约束保证同一 Article 至多一份内容；并不保证每篇 Article 必然有内容。Django 删除收集器的 PROTECT 阻止删除被关联 Article，测试同时确认被保护对象包含 KnowledgeContent。数据库外键提供引用完整性；PROTECT 本身是 ORM 删除策略，不是数据库触发器。

实例保存时比对当前持久关联，并记住已加载/已保存实例主键；即使重新构造同主键实例，改绑也被拒绝。恢复/发布入口另外验证修订归属及 JSON 身份。该保护不覆盖 QuerySet.update、bulk_update、直接 SQL、手工修改内部状态或任意框架调用；没有宣称数据库强制关联永远不可变或已封闭所有发布途径。

publish_for_test 和 restore_draft 使用外层 atomic。本轮在 Wagtail 已写入正式内容后的日志步骤注入异常，验证内容、修订及 Wagtail 日志完整回滚。此结果依赖本实验入口的事务，不代表任意 Revision.publish 调用都满足未来跨模块事务要求；未实现业务审核、审计、Outbox 或并发锁。

直接删除 KnowledgeContent、修订清理、GenericRelation 级联、历史证据永久保留、其他发布途径及原生类方法反序列化等系统性保护仍需后续设计。read_live 仅供程序验证，不是员工接口，没有加入受众、空间、生效时间、下架、归档判断，也未接公开 URL。

## 测试与检查

17 个 test 方法全部通过（最终一次 0.489 秒，不含迁移；subTest 组合不另计）：

1. 空内存库应用全部已有及实验迁移，迁移图无待应用节点，外键检查通过。
2. 一对一数据库唯一约束。
3. 新对象草稿默认值及正式读取为空。
4. 第一份草稿产生修订、不自动发布。
5. V1 正式发布。
6. V2 草稿与正式 V1 隔离。
7. 显式发布 V2 切换正式内容。
8. 恢复追加草稿、延迟发布、稳定身份及历史不变。
9. save/save_revision 拒绝改绑。
10. save/save_revision 拒绝修改已加载主键。
11. 伪造历史 JSON 的 pk/Article 在恢复入口被拒绝。
12. 跨对象修订恢复及发布被拒绝。
13. 缺发布权限或缺发布者时拒绝且数据不变。
14. 发布中途异常完整回滚。
15. 删除 Article 被 PROTECT 拒绝。
16. 拒绝覆盖修订。
17. 重新构造同主键实例也不能改绑。

每个测试结束均重新查询数据库，核对所有旧业务记录快照。模型/迁移一致性：全 App makemigrations --check --dry-run 输出 No changes detected。测试运行器执行 Django system check（含数据库），无错误，108 条警告，0 silenced：97 条 fields.W163（SQLite 不支持字段注释），11 条 models.W046（不支持表注释），均来自现有 accounts/knowledge，不代表 PostgreSQL 通过或失败。

Ruff 静态与格式检查、9 份 Python 文件语法检查、Git 差异及新增文件空白检查通过。首轮生成迁移存在长行，已通过 Ruff 格式化解决；最初文件传递 JSON 解析失败未产生文件，改用原生 UTF-8 写入后完成。本轮没有依赖或业务测试失败遗留。

## 隔离、文件及复跑

run.py 复用 F03A 环境白名单常量，启动 -I 子进程，显式配置；禁止真实 config/dotenv 导入、.env 文件打开、网络连接/DNS、非内存 SQLite。初始化/迁移前断言数据库及测试数据库均为 :memory:，不关闭迁移或屏蔽检查，migrate(run_syncdb=False)。使用既有内存邮件/本地缓存等隔离设置，不启用外部服务。

新增且仅新增本目录 10 个交付文件：

- __init__.py、apps.py、models.py、settings.py、versions.py；
- migrations/__init__.py、migrations/0001_initial.py；
- tests.py、run.py、README.md。

实验迁移仅创建 fusion_f04a.KnowledgeContent，依赖 knowledge.0003_space_audience_policy_comment 和 wagtailcore.0097_baselogentry_uuid_action_timestamp_indexes；未生成正式 knowledge 迁移或改动历史迁移。

```powershell
Set-Location 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
.\.venv\Scripts\python.exe -I -X utf8 experiments/wagtail_f04a/run.py
.\.venv\Scripts\ruff.exe check experiments/wagtail_f04a
.\.venv\Scripts\ruff.exe format --check experiments/wagtail_f04a
git diff --check
```

第一条 Python 命令包含隔离核验、模型/迁移一致性、内存迁移、system check 和 17 项测试。已有迁移无需重新生成。validation.log 与缓存沿用现有忽略规则，不纳入提交。

此前 F01～F03B 文档、实验和角色代码共 25 个文件执行前后 SHA-256 一致。工作区保留全部原有未提交成果，另新增 F04A 目录；暂存区为空。主 worktree 未修改，无提交、推送、Docker、开发库或 PostgreSQL 操作，未进入 F04B/F05。

本轮只验证实验模型和版本机制；程序发布测试不代表审核流程已完成，也不代表员工内容访问已安全接入。
