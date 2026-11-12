# 内网试点生产部署基线 SOP

本 SOP 仅定义未来内网试点的部署合同，不构成服务器、域名、证书、生产数据或上线授权。

## 前置条件

- 使用已审查的 Git 提交构建镜像；不要使用工作区 bind mount。
- 生产 Dockerfile 复用已核验的本地 `opsai-it-web:latest` Linux 基础镜像，并要求一个仓库外的只读 wheelhouse 构建上下文。wheelhouse 必须包含已校验 SHA-256 的 `setuptools-80.9.0-py3-none-any.whl` 与 `gunicorn-27.0.0-py3-none-any.whl`。
- 由负责人提供受控内网域名、可信 HTTPS 证书和仓库外的受控环境文件。
- `PILOT_TLS_CERTS_DIR` 只读目录内必须有 `tls.crt` 与 `tls.key`；密钥不得进入 Git、镜像或日志。
- 每次部署使用独立 Compose 项目和命名卷；不得复用 `opsai-local-demo-*` 或历史 E2E 资源。

## 构建与配置检查

在仓库根目录执行。将示例环境文件复制到仓库外的受控路径后再填写真实值：

```powershell
docker build --progress=plain `
  --build-context wheelhouse=D:\SecureArtifacts\opsai-it-pilot-wheelhouse `
  --file deploy\Dockerfile.production `
  --tag opsai-it-pilot-web:local .

docker compose --env-file D:\SecureConfig\opsai-it-pilot.env `
  --project-name opsai-pilot `
  --file deploy\compose.pilot.yaml config --quiet
```

该 Compose 文件不会把 PostgreSQL 或 Gunicorn 端口发布到宿主机；外部入口仅为受控 Caddy HTTPS 端口。运行前必须确认 `PILOT_HTTPS_DOMAIN`、`DJANGO_ALLOWED_HOSTS` 与 `DJANGO_CSRF_TRUSTED_ORIGINS` 一致。

该构建不访问 PyPI：Dockerfile 使用 `--no-index`，并固定安装 `setuptools==80.9.0` 与 `gunicorn==27.0.0`。部署负责人必须在构建前核对 wheelhouse 的来源和 SHA-256，不能用未验证缓存替代。

## 未来内网部署顺序（需单独授权）

```powershell
docker compose --env-file D:\SecureConfig\opsai-it-pilot.env `
  --project-name opsai-pilot `
  --file deploy\compose.pilot.yaml up -d db media-init static-init web caddy

docker compose --env-file D:\SecureConfig\opsai-it-pilot.env `
  --project-name opsai-pilot `
  --file deploy\compose.pilot.yaml exec -T web python manage.py migrate --noinput

docker compose --env-file D:\SecureConfig\opsai-it-pilot.env `
  --project-name opsai-pilot `
  --file deploy\compose.pilot.yaml exec -T web python manage.py check --deploy
```

执行迁移、创建试点账号、接入证书、开放内网访问以及任何备份恢复演练，都需要未来独立授权。当前基线不验证真实 TLS；HSTS 保持关闭，待真实 HTTPS 证书和客户端兼容性验收通过后才能启用。

## 回滚与停止

- 配置校验、健康检查或安全检查失败时停止，不删除数据卷。
- 应用版本回滚使用经批准的 `git revert` 对应配置提交后重建镜像；不要使用 `reset --hard`。
- 数据库恢复必须使用后续独立的备份恢复任务和新的空闲隔离资源，不能覆盖历史演示或 E2E 卷。
