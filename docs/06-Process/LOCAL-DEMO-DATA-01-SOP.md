# LOCAL-DEMO-DATA-01 独立演示环境操作手册

## 1. 结论与边界

本环境只用于 Windows 本机演示，固定 Compose Project 为 `opsai-local-demo`，网站地址为
`http://127.0.0.1:8001/`。它使用独立容器、网络、数据库卷和媒体卷，不连接或挂载原
`opsai-it` 环境。

严禁把以下资源作为演示命令的目标：

- 原容器 `opsai-it-db-1`、`opsai-it-web-1`；
- 原数据卷 `opsai-it_postgres_data`；
- 原网站 `http://127.0.0.1:8000/`；
- 原备份 `D:\OpsAI-Backups\Database\OpsAI_迁移前备份_20261029-222705.dump`。

演示环境只启动 PostgreSQL、一次性媒体目录初始化容器和 Django Web，不启动通知 Worker，
不配置钉钉、邮件或 Webhook 凭据。工作流 Outbox 只保存在演示数据库中，不会自动投递。

## 2. 固定资源

| 类型 | 固定身份 |
| --- | --- |
| Compose Project | `opsai-local-demo` |
| Web | `opsai-local-demo-web-1`，仅发布 `127.0.0.1:8001` |
| PostgreSQL | `opsai-local-demo-db-1`，不发布宿主机端口 |
| 媒体初始化 | `opsai-local-demo-media-init-1`，正常状态为执行后退出 0 |
| 数据库卷 | `opsai-local-demo-postgres-data` |
| 私有媒体卷 | `opsai-local-demo-private-media` |
| 网络 | `opsai-local-demo-network` |
| 数据库名 | `opsai_local_demo` |
| 实际配置 | `D:\Temp\OpsAI-Local-Demo-Config\local-demo.env`（不入 Git） |

## 3. 首次启动

在 PowerShell 中进入仓库根目录。先确认分支、完整 HEAD、工作区和原网站：

```powershell
Set-Location -LiteralPath 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
git branch --show-current
git rev-parse HEAD
git status --short
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/live'
```

把配置样例复制到仓库外目录，随后人工填入新的随机演示专用值。不得复制根 `.env`，也不得
在终端、日志或截图中打印实际值：

```powershell
New-Item -ItemType Directory -Path 'D:\Temp\OpsAI-Local-Demo-Config' -ErrorAction SilentlyContinue
Copy-Item -LiteralPath 'deploy\local-demo.env.example' -Destination 'D:\Temp\OpsAI-Local-Demo-Config\local-demo.env'
notepad 'D:\Temp\OpsAI-Local-Demo-Config\local-demo.env'
```

当前 Docker 容器网络不能访问 PyPI，因此 Compose 的内联构建只复用本机已核验的
`opsai-it-web:latest` Python 依赖层，清空旧 `/app` 后复制当前源码，生成新的演示镜像。
启动前必须核对依赖镜像身份；不一致时停止，不能静默改用未知镜像：

```powershell
docker image inspect opsai-it-web:latest --format '{{.Id}}'
```

DATA-01 实际验收使用的依赖镜像 ID 为：

```text
sha256:d98081097d6da4b6312e97b6e2a52ef501c72ef0f3c654d46d8ab2d768e2b130
```

定义固定 Compose 参数并校验配置：

```powershell
$DemoCompose = @(
  '--project-name', 'opsai-local-demo',
  '--env-file', 'D:\Temp\OpsAI-Local-Demo-Config\local-demo.env',
  '-f', 'deploy\compose.local-demo.yaml'
)

docker compose @DemoCompose config --quiet
docker compose @DemoCompose build web
```

首次创建空库、迁移和检查：

```powershell
docker compose @DemoCompose up -d db
docker compose @DemoCompose run --rm --no-deps media-init
docker compose @DemoCompose run --rm --no-deps web python manage.py migrate --noinput
docker compose @DemoCompose run --rm --no-deps web python manage.py check
docker compose @DemoCompose run --rm --no-deps web python manage.py showmigrations --plan
```

确认迁移全部应用后，初始化文章并再次执行一次验证幂等性：

```powershell
docker compose @DemoCompose run --rm --no-deps web python manage.py seed_local_demo_article
docker compose @DemoCompose run --rm --no-deps web python manage.py seed_local_demo_article
```

第二次应输出 `created: 0; existing: 1; conflict: 0`。随后启动 Web：

```powershell
docker compose @DemoCompose up -d web
```

## 4. 日常启动与停止

日常重新启动：

```powershell
Set-Location -LiteralPath 'D:\Desktop\OpsAI\AI-OpsAI-IT-wagtail-poc'
$DemoCompose = @(
  '--project-name', 'opsai-local-demo',
  '--env-file', 'D:\Temp\OpsAI-Local-Demo-Config\local-demo.env',
  '-f', 'deploy\compose.local-demo.yaml'
)
docker compose @DemoCompose up -d
```

停止演示环境但保留容器和数据卷：

```powershell
docker compose @DemoCompose stop
```

不得使用 `down -v`、`docker volume prune` 或全局 Docker 清理命令。若确需删除演示资源，
必须先逐项核验 `com.docker.compose.project=opsai-local-demo` 标签并取得新的明确授权。

## 5. 隔离与健康检查

检查容器、卷、网络与端口：

```powershell
docker ps -a --filter 'label=com.docker.compose.project=opsai-local-demo'
docker volume ls --filter 'label=com.opsai.task=LOCAL-DEMO-DATA-01'
docker network ls --filter 'label=com.opsai.task=LOCAL-DEMO-DATA-01'
docker port opsai-local-demo-web-1 8000/tcp
docker inspect opsai-local-demo-web-1 --format '{{json .Mounts}}'
docker inspect opsai-local-demo-db-1 --format '{{json .Mounts}}'
```

预期 Web 只显示 `127.0.0.1:8001`，数据库没有宿主端口；Web 只挂载
`opsai-local-demo-private-media`，数据库只挂载 `opsai-local-demo-postgres-data`，不得出现项目源码
bind mount、原数据卷或原网络。

检查 Django 与媒体目录：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8001/health/live'
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8001/health/ready'
docker compose @DemoCompose exec -T web python manage.py check
docker compose @DemoCompose exec -T web sh -c 'test -w /app/private_media'
```

两项健康检查都必须返回 200。不得修改健康检查代码或忽略 `private_media` 失败。

## 6. 演示身份与业务路径

三个业务流程身份均为独立、非 superuser、不可用密码的本地开发身份，通过
`http://127.0.0.1:8001/dev/login/` 切换：

- `dev_editor`：知识编辑员，创建并提交文章；
- `dev_reviewer`：知识审核员，只在已授权的演示空间独立审核；
- `dev_employee`：普通员工，只属于演示内容受众组，用于搜索和阅读正式内容。

既有安全命令还会创建 `dev_knowledge_admin` 辅助身份，用于 Django Admin 只读查看文章与版本；
它不是 superuser，不参与编辑、提交或批准。同一身份不得同时承担编辑与审核。

业务服务链为：

```text
create_article
→ manual_save_draft
→ submit_article_for_review
→ approve_and_publish_article_version
→ 员工首页 / 搜索 / 详情
```

演示文章为《网络打印机无法打印——故障排查 SOP（演示）》，知识编号 `KB-000001`。
服务层完成审核并不代表审核 Web 页面已完成；当前审核 Web 页面仍为 `NOT IMPLEMENTED`。

## 7. 备份与恢复验证

备份只允许写入仓库外演示目录：

```powershell
$BackupDir = 'D:\OpsAI-Backups\Database\LocalDemo'
New-Item -ItemType Directory -Path $BackupDir -ErrorAction SilentlyContinue
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Name = "OpsAI_本地演示_DATA01_$Stamp.dump"

docker exec opsai-local-demo-db-1 pg_dump `
  -U opsai_local_demo_app -d opsai_local_demo -Fc -f "/tmp/$Name"
docker cp "opsai-local-demo-db-1:/tmp/$Name" (Join-Path $BackupDir $Name)
Get-FileHash -LiteralPath (Join-Path $BackupDir $Name) -Algorithm SHA256
```

恢复验收必须使用新的临时数据库，绝不能把目标写成 `opsai_local_demo` 或原业务数据库：

```powershell
$RestoreDb = 'opsai_local_demo_restore_verify'
docker exec opsai-local-demo-db-1 createdb -U opsai_local_demo_app $RestoreDb
docker exec opsai-local-demo-db-1 pg_restore `
  -U opsai_local_demo_app -d $RestoreDb --exit-on-error "/tmp/$Name"
docker exec opsai-local-demo-db-1 psql `
  -U opsai_local_demo_app -d $RestoreDb -c '\dt'
```

只有恢复和记录核对通过后，才可删除这个精确临时数据库：

```powershell
docker exec opsai-local-demo-db-1 dropdb -U opsai_local_demo_app $RestoreDb
```

DATA-01 已验证备份：

```text
D:\OpsAI-Backups\Database\LocalDemo\OpsAI_本地演示_DATA01_20261030-001653.dump
SHA-256: 61C7A887031219339D6A8E752C777E855A74D22673095080985F0412303CB3A2
```

## 8. 常见问题

### 构建访问 PyPI 超时

当前 Docker Desktop 配置中的代理不可达，现有 Dockerfile 的 `pip install` 可能在 PyPI TLS 握手处
超时。本任务没有修改 Dockerfile，而是固定复用经 `pip check` 验证的本地依赖镜像。若该镜像 ID
漂移或不存在，停止构建并重新评估依赖来源；不要复制原 `.env`，也不要临时关闭安全检查。

### `/health/ready` 返回 503

检查 `opsai-local-demo-private-media` 是否挂载到 `/app/private_media`，并确认 UID 10001 可写。
重新执行 `media-init` 后再启动 Web，不得强制 readiness 返回 200。

### 8001 无法访问

用 `Get-NetTCPConnection -LocalPort 8001` 检查端口占用，再用 `docker port` 确认映射。数据库健康但
Web 不可达时查看：

```powershell
docker compose @DemoCompose logs --tail 100 web
```

### 初始化命令拒绝执行

命令会核验 DEBUG、本地开发登录、Compose 标识、授权基线、数据库名、服务地址、实际 PostgreSQL
身份和镜像内根 `.env`。任何一项不符都会失败关闭；不得修改布尔值或绕过门禁。

## 9. 确认原环境不受影响

演示前后均执行：

```powershell
docker inspect opsai-it-db-1 --format '{{.Id}} {{.State.Status}}'
docker inspect opsai-it-web-1 --format '{{.Id}} {{.State.Status}}'
docker volume inspect opsai-it_postgres_data --format '{{.Name}} {{.Mountpoint}}'
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/live'
```

原容器 ID、原卷身份、8000 健康状态或原备份摘要出现变化时，立即停止演示并保留现场证据。
