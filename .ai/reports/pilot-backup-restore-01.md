# PILOT-BACKUP-RESTORE-01 验收报告

> 状态：执行中。本文只记录本任务的隔离合成数据演练，不记录或包含真实数据库凭据、真实员工数据或生产备份。

## 1. 预检

- 基线：`d5c1e80f248f492a02428d26a2ac8dcfa74884f1`，分支 `fusion/wagtail-poc`。
- 前置：`PILOT-PRODUCTION-DEPLOYMENT-BASELINE-01` 已 `DONE / PASS`。
- 现有历史 Docker 容器与 Volume 均只读保护；本任务将仅创建 `opsai-backup-restore-01-*` 前缀的新资源。

## 2. 设计证据

- `deploy/backup/pg_backup.ps1`：custom-format 逻辑备份、仓库外路径拒绝、SHA-256 和版本/耗时清单。
- `deploy/backup/pg_restore.ps1`：清单哈希验证、全新前缀数据库、拒绝覆盖、`pg_restore --exit-on-error`。
- 合成夹具和恢复验证脚本：覆盖员工、已发布知识、版本、审核、受众和反馈的关联。

## 3. 实际隔离演练结果

### 3.1 隔离资源

- 网络：`opsai-backup-restore-01-net`（Docker internal network）。
- 源库：容器 `opsai-backup-restore-01-source-db`、Volume `opsai-backup-restore-01-source-volume`、数据库 `opsai_backup_restore_source`。
- 恢复库：容器 `opsai-backup-restore-01-restore-db`、Volume `opsai-backup-restore-01-restore-volume`、数据库 `opsai_backup_restore_verify`。
- 两个容器均使用 `postgres:17.11-alpine3.24`，未发布宿主机端口；未操作 `opsai-local-demo-*`、历史 E2E 或生产基线资源。
- 合成夹具仅写入源库，并设置 `OPSAI_BACKUP_RESTORE_DRILL=true` 与数据库名前缀双门禁。

### 3.2 备份与完整性

- 实际备份：`D:\Temp\OpsAI-Backup-Restore-01\backup\opsai-postgresql-20261112T151304Z.dump`。
- 格式：`pg_dump custom`；PostgreSQL / `pg_dump` 均为 `17.11`。
- 文件大小：`159,844` bytes。
- SHA-256：`84B41EE5705070F6D26865CD75EA0E7B860ACE2176F7585B5ABE9CAF1FDEB93E`。
- 备份耗时：`0.492` 秒；退出码：`0`。
- 对应清单：同目录 `opsai-postgresql-20261112T151304Z.manifest.json`，记录格式、版本、时间、大小、哈希和退出码，不包含密码。

### 3.3 恢复与业务一致性

- 恢复耗时：`0.793` 秒；退出码：`0`；恢复前重新计算的 SHA-256 与清单一致。
- 源库与恢复库均通过业务验证：`accounts_user=3`、`kb_article=1`、`kb_article_version=1`、`kb_review_record=1`、`kb_article_audience=1`、`kb_feedback_record=1`。
- 恢复后确认：员工存在；`KB-900001` 指向已发布版本；审核批准记录、对合成员工的受众允许规则、以及该员工到该文章已发布版本的 `resolved` 反馈均存在。
- 结论：恢复的数据数量和关键关联与备份源一致；不是仅依据 `pg_restore` 返回码判定。

### 3.4 负向与保护验证

- 篡改副本：对仓库外副本追加一个字节后，恢复脚本在创建目标库前拒绝 SHA-256 不匹配；`opsai_backup_restore_tamper` 未被创建。
- 已存在目标：再次指定 `opsai_backup_restore_verify` 时，恢复脚本拒绝覆盖；恢复库的六项计数保持 `3|1|1|1|1|1`。
- 这些验证证明脚本不会因目标库名称复用或备份内容被改动而自动覆盖数据。

### 3.5 自动检查

- PowerShell 5.1 语法检查：`pg_backup.ps1`、`pg_restore.ps1` 通过。
- 相关自动测试：`79 passed, 3 subtests passed`（脚本合同、员工反馈与受众选择器回归）。
- `manage.py check --settings=config.settings.test`、`makemigrations --check --dry-run --settings=config.settings.test`、Ruff lint/format、`compileall` 与 `git diff --check` 均通过。

## 4. 证据与范围

- 原始证据目录：`D:\Temp\OpsAI-Backup-Restore-01\evidence`；其中包含隔离资源身份、源/恢复业务验证、备份/恢复结果和两类拒绝日志。
- 备份文件仅在仓库外目录保存，未被 Git 跟踪或提交。
- 本演练未备份私有媒体 Volume 或附件；当前结论只覆盖 PostgreSQL 逻辑数据。附件启用前必须另行实现并演练媒体/对象存储的加密、哈希、保留与恢复流程。
- 建议试点初期每天全量逻辑备份，并在发布或迁移前额外备份；保留至少 7 个日备份和 4 个周备份。建议 RPO ≤ 24 小时、RTO ≤ 4 小时，均为待真实容量、存储与恢复测量确认的建议而非承诺。
