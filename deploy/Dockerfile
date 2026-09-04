# OpsAI-IT 本地开发镜像（仅用于本地开发，不用于生产部署）
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先只复制依赖声明，利用镜像层缓存；README 是 pyproject.toml 声明的 readme 文件
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

# 复制项目源码（.dockerignore 已排除 .env、.venv、.git 等）
COPY . .

# 私有附件目录（运行时被 bind mount 覆盖，独立构建时保证存在）
RUN mkdir -p /app/private_media

# 尽量以非 root 用户运行
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
