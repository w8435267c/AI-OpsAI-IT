# OpsAI-IT Django 单体项目模块目录规划

## 1. 推荐目录

```text
AI-OpsAI-IT/
├── manage.py
├── pyproject.toml
├── .env.example
├── README.md
├── config/                         # Django 项目配置，不放业务模型
│   ├── __init__.py
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py                 # 公共配置
│       ├── development.py          # 本地开发配置
│       ├── test.py                 # 自动化测试配置
│       └── production.py           # 正式环境配置
├── apps/
│   ├── core/                       # 公共基类、异常、健康检查、通用工具
│   │   ├── models.py
│   │   ├── exceptions.py
│   │   ├── middleware.py
│   │   └── health.py
│   ├── accounts/                   # 用户、部门、内容用户组、系统角色
│   │   ├── models.py               # User、Department、UserDepartment、UserGroup 等
│   │   ├── services.py             # 用户同步、禁用、角色授权
│   │   ├── selectors.py            # 用户和组织查询
│   │   ├── admin.py
│   │   └── tests/
│   ├── knowledge/                  # 知识库核心领域
│   │   ├── models.py               # Article、ArticleVersion、ArticleAudience、ReviewRecord 等
│   │   ├── services.py             # 创建草稿、提交审核、发布、下架、复审
│   │   ├── selectors.py            # 可见知识、详情、版本历史查询
│   │   ├── forms.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── validators.py
│   │   └── tests/
│   ├── search/                     # 检索与搜索质量
│   │   ├── models.py               # SearchLog、同义词等
│   │   ├── services.py             # 权限过滤、检索、排序、高亮
│   │   ├── selectors.py
│   │   └── tests/
│   ├── workflow/                   # 状态流转和后台任务
│   │   ├── services.py             # 审核状态机、事务边界
│   │   ├── outbox.py               # 通知 Outbox 入队与幂等
│   │   ├── tasks.py                # 复审提醒、通知重试、索引重建
│   │   └── tests/
│   ├── dingtalk/                   # 钉钉适配层
│   │   ├── client.py               # 钉钉服务端 API 客户端
│   │   ├── jsapi.py                # H5 JSAPI 配置与签名
│   │   ├── auth.py                 # 免登授权码换取可信身份
│   │   ├── services.py             # 通讯录同步、工作通知
│   │   ├── views.py                # 免登、回调、健康检查接口
│   │   ├── urls.py
│   │   └── tests/
│   ├── service_desk/               # 统一 IT 服务入口集成
│   │   ├── models.py               # ServiceJumpLog、ContextToken
│   │   ├── services.py             # 生成安全上下文、字段映射、跳转降级
│   │   ├── views.py
│   │   └── tests/
│   └── audit/                      # 审计与合规日志
│       ├── models.py               # AuditLog
│       ├── services.py
│       ├── middleware.py
│       └── tests/
├── templates/                      # Django Templates 页面
│   ├── base.html
│   ├── errors/
│   ├── knowledge/
│   ├── search/
│   └── workflow/
├── static/                         # Bootstrap、HTMX、钉钉 JSAPI、自有 CSS/JS
│   ├── css/
│   ├── js/
│   └── images/
├── private_media/                  # 私有附件，仅通过鉴权视图访问
├── tests/                          # 跨 App 集成测试和端到端测试
├── deploy/
│   ├── compose.yaml
│   ├── compose.production.yaml
│   ├── Caddyfile
│   └── scripts/
└── docs/
    ├── 04-Architecture/
    ├── 05-Database/
    ├── 06-Process/
    └── 07-ADR/
```

## 2. 各 App 的职责边界

| App | 应负责 | 不应负责 |
| --- | --- | --- |
| `accounts` | 平台用户、部门、多部门关系、内容用户组、系统角色和账号状态 | 钉钉 HTTP 请求、知识可见性查询 |
| `knowledge` | 知识空间、分类、文章、版本、受众、审核记录、附件元数据 | 直接发送钉钉通知、直接跳转 OA |
| `search` | 查询规范化、同义词、权限过滤后的检索、排序、高亮、搜索日志 | 修改文章状态或发布版本 |
| `workflow` | 状态转换、事务、幂等、Outbox、定时任务 | 钉钉接口细节、页面渲染 |
| `dingtalk` | 免登、用户映射、通讯录同步、工作通知和回调适配 | 决定知识是否可以发布 |
| `service_desk` | `context_token`、字段映射、服务跳转和失败降级 | 建设完整 ITSM 生命周期 |
| `audit` | 敏感操作审计、请求上下文、变更前后快照 | 业务状态机 |
| `core` | 无业务含义的公共能力 | Article、User 等领域模型 |

## 3. 代码组织约定

1. `views.py` 只处理 HTTP 输入输出，不编写发布、审核等核心业务规则。
2. 所有状态变化写入 `services.py`，并使用 `transaction.atomic()` 保证文章、版本、审核记录和 Outbox 同时成功或同时失败。
3. 跨表复杂读取放在 `selectors.py`；搜索结果必须先做服务端受众权限过滤。
4. 钉钉接口统一从 `dingtalk.client` 调用，AppSecret 不进入前端、数据库普通字段或 Git。
5. 不使用 Django Signal 驱动发布、审核等核心流程，避免调用链隐蔽；Signal 只用于低风险的附属动作。
6. `Article.current_published_version` 和 `latest_working_version` 只能由 `knowledge.services` 或 `workflow.services` 修改。
7. 正式业务数据不硬删除；文章采用下架、归档，用户采用禁用、离职状态，版本和审核记录永久保留。
8. `models.py` 的 `clean()` 用于对象级校验，服务层保存前应显式调用 `full_clean()`；数据库约束负责兜底可在单表内表达的规则。

## 4. 当前 models.py 的外部依赖

本次 `knowledge/models.py` 默认项目已经设置：

```python
AUTH_USER_MODEL = "accounts.User"
```

并且 `accounts.models` 至少提供：

```python
class Department(models.Model):
    ...

class UserGroup(models.Model):
    ...
```

其中 `UserGroup` 是“内容受众用户组”，不能直接等同于系统操作角色。系统角色仍使用独立的 RBAC 关系管理。

## 5. 下一步建议

1. 先实现 `accounts.User`、`Department`、`UserDepartment`、`UserGroup`。
2. 将本次 `knowledge/models.py` 放入 `apps/knowledge/models.py`。
3. 创建并检查迁移：`python manage.py makemigrations accounts knowledge`。
4. 实现 `knowledge.services.publish_version()`，在一个事务中完成旧版本替代、新版本发布和 Article 指针更新。
5. 再实现带受众过滤的查询和搜索，禁止前端直接决定部门、角色或知识可见范围。
