# Task 13 审核发布 Web 端到端验收报告

## 结论

`TASK13-REVIEW-WEB-E2E-01` 已完成，结论为 `DONE / PASS`。本报告只覆盖隔离环境验收，不代表 Task 13 主任务完成、生产上线或钉钉接入获授权。

## 基线与原始证据

- 执行基线：`01529d2a23c7e2c46bb81fa984eb838080eeb63f`
- 分支：`fusion/wagtail-poc`
- 原始证据：`D:\Temp\OpsAI-Task13-E2E-01\evidence\TEST_EVIDENCE.md`
- 原始证据 SHA-256：`43B600CEB6410A503276A1DA37534D50BCE2627DA4810253D1A665F921ABF989`
- 隔离 Compose 项目：`opsai-task13-e2e-01`
- 隔离地址：`http://127.0.0.1:18013`

## 验收结果

1. 阶段 01 部署验证：PASS。隔离迁移、`manage.py check`、`/health/live`、`/health/ready` 通过；未登录审核访问被拒绝。
2. 阶段 02 业务闭环：PASS。合成编辑创建并提交知识，合成审核员批准发布或驳回，合成员工可搜索并读取正式知识。
3. 阶段 03 安全与异常：PASS。未登录、越权、自审、重复提交被拒绝；驳回内容对员工搜索和直链均不可见；并发与幂等由隔离 PostgreSQL 定向回归覆盖。
4. 阶段 04 浏览器：PASS。桌面 `1280 × 720` 审核队列可见；手机 `390 × 844` 的审核、搜索和详情页面无横向溢出，表单和审批按钮可访问。
5. 阶段 05 最终核验：PASS。`KB-000001` 已发布、`KB-000002` 已驳回、`KB-000003` 保持待审核自审限制现场。

## PostgreSQL 定向回归

在隔离 Compose Web 容器中执行：

```text
python manage.py test apps.workflow.tests.test_pg_concurrency \
  apps.workflow.tests.test_review_web \
  apps.workflow.tests.test_submit_service \
  apps.workflow.tests.test_approve_publish_service \
  apps.workflow.tests.test_reject_service \
  apps.knowledge.tests.test_manage_article_create \
  apps.knowledge.tests.test_task13_review_foundation -v 1
```

结果：`Ran 114 tests ... OK`。

## 安全边界

- 仅使用合成账号、合成知识、独立 PostgreSQL 卷与独立私有媒体卷。
- 未修改业务代码、任务外文件、真实凭据、生产数据库或历史 Task 13-07/13-08 证据。
- `opsai-local-demo-web-1`、`opsai-local-demo-db-1` 及其保护卷未停止、未重建、未覆盖。
- 隔离容器、卷和原始证据保留，未自动清理。

## 主任务状态

Task 13 主任务保持 `BACKLOG / unassigned`。仍缺 Outbox Worker/通知发送、原持久数据库迁移前置检查及负责人对完整主任务范围的独立验收。
