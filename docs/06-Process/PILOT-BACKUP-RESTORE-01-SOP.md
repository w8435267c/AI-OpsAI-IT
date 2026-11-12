# PILOT-BACKUP-RESTORE-01：PostgreSQL 备份与独立恢复 SOP

## 1. 适用范围和边界

本 SOP 定义 OpsAI-IT PostgreSQL 的逻辑备份和**全新隔离数据库**恢复流程。它不授权覆盖源库、生产恢复、Docker Volume 删除或读取真实凭据。备份与恢复均须由具备单独环境授权的运维人员执行。

- 备份格式：`pg_dump` custom format（`.dump`），便于 `pg_restore --exit-on-error` 恢复。
- 备份目录：必须在仓库外的受控目录，例如 `D:\OpsAI-Backups\PostgreSQL`；脚本拒绝写入仓库。
- 密码：仅由已运行数据库容器的受控环境提供；命令、清单、报告和 Git 不记录密码。
- 媒体边界：数据库逻辑备份**不包含**`private_media` Volume、附件或任何外部对象存储。试点未启用附件时也必须单独记录；启用后应为私有媒体建立独立、可校验、可恢复的备份链。

## 2. 备份步骤

先确认目标容器、数据库名和角色名均为已批准的隔离或生产身份，且输出目录不在仓库中。示例只展示变量名，不展示凭据：

```powershell
pwsh -File deploy/backup/pg_backup.ps1 `
  -SourceContainer <approved-postgres-container> `
  -Database <approved-database> `
  -DatabaseUser <approved-role> `
  -OutputDirectory 'D:\OpsAI-Backups\PostgreSQL'
```

脚本在容器内生成 custom dump，再以 `docker cp` 导出，避免 PowerShell 文本重定向损坏二进制文件。成功后同目录会得到：

- `opsai-postgresql-<UTC>.dump`
- `opsai-postgresql-<UTC>.manifest.json`

清单包含开始/完成时间、耗时、退出码、数据库服务器版本、`pg_dump` 版本、文件大小与 SHA-256。恢复前必须重新计算 SHA-256 并与清单一致。

## 3. 独立恢复步骤

恢复目标必须是新建的 PostgreSQL 容器和新建 Docker Volume。目标数据库名须使用 `opsai_backup_restore_` 前缀，且恢复前不存在；脚本会拒绝已有同名数据库，绝不执行 `dropdb` 或覆盖。

```powershell
pwsh -File deploy/backup/pg_restore.ps1 `
  -DumpPath 'D:\OpsAI-Backups\PostgreSQL\opsai-postgresql-<UTC>.dump' `
  -ManifestPath 'D:\OpsAI-Backups\PostgreSQL\opsai-postgresql-<UTC>.manifest.json' `
  -TargetContainer <new-isolated-postgres-container> `
  -TargetDatabase opsai_backup_restore_verify `
  -DatabaseUser <approved-role>
```

恢复成功还必须运行面向业务记录的恢复后验证，至少比较员工账号、已发布文章与版本、审核记录、受众规则、反馈记录及其关联；仅 `pg_restore` 退出码为 0 不足以判定成功。

## 4. 失败处理

- 备份失败、空文件或 SHA-256 不匹配：停止恢复，保留原始日志与文件，不修改源库。
- 恢复目标已存在、`pg_restore` 失败或业务数据比较失败：停止，不清理目标容器或 Volume，保留现场供调查；不得以原目标重复恢复。
- 任何来源不明的容器、数据库、备份清单或路径：停止并由负责人重新确认。

## 5. 建议的试点运行策略（非承诺）

建议内网试点初期每天至少一次逻辑全量备份，并在每次应用发布或数据库迁移前额外备份；保留至少 7 个日备份和 4 个周备份，具体周期需由数据责任人与存储容量评估确认。建议目标为 RPO 不超过 24 小时、RTO 不超过 4 小时；这是待容量、网络、加密存储和实测恢复时长验证的**建议目标，不是服务承诺**。

备份目录应使用受控 ACL、静态加密与独立保留策略；应定期在新的隔离环境做恢复演练并保存哈希、恢复耗时和业务一致性证据。
