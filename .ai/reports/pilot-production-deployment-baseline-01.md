# PILOT-PRODUCTION-DEPLOYMENT-BASELINE-01 验收报告

状态：`DONE / PASS（仅限本地隔离生产部署配置基线）`

本报告仅记录本地生产部署配置基线的验证结果。它不代表真实内网部署、真实 HTTPS 证书、生产数据库、真实钉钉或真实员工账号已经验收。

## 验收边界

- 生产 Web 镜像使用 Linux Python 3.13、Gunicorn 和现有 `config.wsgi:application`。
- Caddy 只发布 HTTPS 入口；Gunicorn 与 PostgreSQL 仅位于内部 Docker 网络。
- 静态文件由 `static-init` 收集后只读挂载给 Caddy；`/media/` 由 Caddy 直接返回 404。
- 关键环境变量缺失时 Compose 或 Django production settings 必须失败关闭。

## 待记录的验证

- Dockerfile、Compose 与 Caddy 配置静态检查。
- Linux 镜像内 Gunicorn、Django `check --deploy` 与生产安全设置检查。
- 相关认证、搜索、知识访问回归，以及 Git、Ruff 和格式检查。

实际执行命令、退出码、镜像标识与限制将在验证阶段追加；未执行的项目不得标记为通过。

## 已执行的离线验证

- `pytest tests/test_production_deployment_baseline.py -q`：`7 passed`。
- 使用合成环境变量执行 `python manage.py check --deploy --fail-level ERROR`：退出码为 0。Django 输出两条预期告警：合成 `SECRET_KEY` 不满足生产强度，以及为避免未验证 TLS 造成不可逆访问风险，`SECURE_HSTS_SECONDS=0`。
- `python manage.py check --settings=config.settings.test`：通过。

## 已解除的镜像构建阻塞

- 正常构建命令：`docker build --progress=plain --tag opsai-pilot-baseline-01-web:local --file deploy/Dockerfile.production .`。
- 正常构建退出码：`1`。Docker 内访问 PyPI 获取 `setuptools>=77` 时发生五次 15 秒读取超时；原始 stdout/stderr/退出码保留于 `D:\Temp\OpsAI-Pilot-Production-Baseline-01\evidence\build-20261111-01`。
- 受控回退：从官方 PyPI wheel 链接下载并核验仓库外 wheelhouse：`gunicorn-27.0.0-py3-none-any.whl` SHA-256 为 `1380f2f520abc3beb9e72cd2e728bd2d08a19b3ff6ac03ebd8da71d1798a4008`；`setuptools-80.9.0-py3-none-any.whl` SHA-256 为 `062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922`。
- 回退构建命令：`docker build --network none --progress=plain --build-context wheelhouse=D:\Temp\OpsAI-Pilot-Production-Baseline-01\wheelhouse --tag opsai-pilot-baseline-01-web:local --file deploy/Dockerfile.production .`。
- 回退构建退出码：`0`；`pip check` 通过。完整日志和退出码保留于 `D:\Temp\OpsAI-Pilot-Production-Baseline-01\evidence\build-20261111-03-wheelhouse-offline`。

## 已通过的隔离运行验证

- 隔离 Compose 项目：`opsai-pilot-baseline-validation-01`；仅创建其专属 PostgreSQL、私有媒体、静态文件卷和内部网络，未触碰既有演示/E2E 资源。
- 应用迁移在该隔离 PostgreSQL 数据库完成；数据库仅显示容器内 `5432/tcp`，无宿主机端口发布。
- Web 容器以 UID `10001` 运行，进程为 Gunicorn + `config.wsgi:application`；源码目录未 bind mount，`.env` 和 `.git` 不在容器应用目录内。
- 通过受控 `X-Forwarded-Proto: https` 请求：`/health/live` 返回 200，`/health/ready` 返回 200 且数据库/私有媒体检查均为 true；`/dev/login/` 返回 404。
- 缺少 `DJANGO_SECRET_KEY` 时 production settings 拒绝启动，命令退出码为 1。

## 当前阻塞

- `docker pull caddy:2.10.2-alpine` 退出码为 `1`。Docker Desktop 配置的 HTTPS 代理不可达，无法连接 Docker Hub；原始 stdout/stderr/退出码保留于 `D:\Temp\OpsAI-Pilot-Production-Baseline-01\evidence\caddy-pull-20261111-01`。
- 因 Caddy 镜像无法获得，未能执行 Caddyfile 语法验证、合成 TLS 反向代理、静态文件经 Caddy 提供及 `/media/` 直接访问拒绝的实际验收。
- 因而本任务不得标记 PASS，也不得提交当前配置成果。恢复需要可信的本地 Caddy `2.10.2-alpine` 镜像或获批准的 Docker 代理修复，再执行一次新的 Caddy 验证。

## 追加本地质量检查

- `pytest tests/test_production_deployment_baseline.py apps/accounts/tests/test_employee_login.py apps/accounts/tests/test_dev_login.py apps/knowledge/tests/test_employee_home.py apps/search/tests -q`：`99 passed, 37 subtests passed`，退出码 `0`。
- `python manage.py check --settings=config.settings.test`：通过；`python manage.py makemigrations --check --dry-run --settings=config.settings.test`：`No changes detected`。
- `ruff check config/settings/production.py tests/test_production_deployment_baseline.py`：通过；`ruff format --check config/settings/production.py tests/test_production_deployment_baseline.py`：两个文件均已格式化。
- `git diff --check`：通过。以上检查不替代尚未执行的 Caddy/HTTPS 运行验收。

## 2026-11-12：Caddy 阻塞解除与最终隔离验收

- 已核验本地 `caddy:2.10.2-alpine` 镜像：Linux/amd64，镜像 ID 与摘要均为 `sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d`。
- 为 Caddy 增加独立入口网络；PostgreSQL 与 Gunicorn 仍仅连接内部 `backend` 网络。该调整使 Caddy 的受控 `127.0.0.1:18080` 和 `127.0.0.1:18443` 端口可被 Docker Desktop 正确发布。
- 使用仓库外临时自签名证书完成 TLS 1.3 握手；通过显式 `--cacert` 校验证书链，未修改 Windows 全局证书信任。证书 SHA-256：`D1DBDDAC8040E02F63BC10933D69AB8935FD65EF7508AC0A3094C28125E35C1A`。
- HTTP 请求实际返回 301 并导航到受控 HTTPS 端口；`/health/live`、`/health/ready`、经 Caddy 提供的 `/static/css/opsai.css` 均返回 200；`/media/probe.txt` 返回 404；`/dev/login/` 返回 404；未认证员工首页返回 401。
- Caddy 覆盖客户端伪造的 `X-Forwarded-Proto`，后端 Web 与数据库均未发布宿主机端口。缺少 `DJANGO_SECRET_KEY` 且明确加载 production settings 时，命令退出码为 1 并拒绝启动。
- 最终质量检查：相关 pytest `99 passed, 37 subtests passed`；部署专项 `7 passed`；Django test check、迁移一致性、Ruff lint/format 和 `git diff --check` 均通过。production `check --deploy --fail-level ERROR` 退出码为 0，仅保留 HSTS 尚未在真实公司域名/证书验收前启用的预期警告。

## 最终边界

- 本次 PASS 仅证明本地隔离 Docker、合成 PostgreSQL、合成域名与临时 TLS 证书下的生产部署配置基线；不代表公司内网、真实域名、真实证书、真实数据库或真实员工试点已上线。
- 原始 Caddy 拉取失败记录及其证据保持保留；本次未删除、覆盖或修改历史演示/E2E 资源。
- 功能提交：`3b504ab85c48b8b1ceb617f4b9fe9f10f63d8efc`；任务元数据收口提交将在本报告与任务状态审查通过后单独创建。
