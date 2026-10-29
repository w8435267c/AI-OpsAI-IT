"""在严格隔离的本地演示环境中创建并发布首篇演示知识。"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import UserGroup
from apps.accounts.roles import DEV_IDENTITIES, dev_user_deviation
from apps.audit.models import AuditEvent
from apps.knowledge.management.commands.seed_demo_data import (
    DEMO_CATEGORY_CODE,
    DEMO_GROUP_NAME,
    DEMO_SPACE_CODE,
)
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    Category,
    KnowledgeSpace,
    ReviewDecision,
    ReviewerSpaceScope,
    ReviewRecord,
    VersionStatus,
)
from apps.knowledge.services import create_article, manual_save_draft
from apps.workflow.models import (
    IdempotencyStatus,
    WorkflowIdempotencyRecord,
    WorkflowOutboxEvent,
    WorkflowOutboxStatus,
)
from apps.workflow.services import (
    approve_and_publish_article_version,
    submit_article_for_review,
)

EXPECTED_PROJECT = "opsai-local-demo"
EXPECTED_INSTANCE = "local-demo-data-01"
EXPECTED_DATABASE = "opsai_local_demo"
EXPECTED_DATABASE_HOST = "db"
AUTHORIZED_BASE_HEAD = "04d9cea907d3b35e143a3475568aa05291115243"

DEMO_TITLE = "网络打印机无法打印——故障排查 SOP（演示）"
DEMO_SUMMARY = "【DEMO】用于本地知识库演示的网络打印机排障流程，不含真实生产配置。"
DEMO_INITIAL_BODY = "【DEMO】网络打印机排障文章初始草稿，待编辑者完成正式演示内容。"
DEMO_BODY_TEXT = """【DEMO】网络打印机无法打印——故障排查 SOP

一、故障现象
用户发送打印任务后没有出纸，打印队列长时间停留，或系统提示打印机脱机。

二、常见原因
常见原因包括终端网络异常、打印机离线、地址或端口配置错误、打印队列阻塞、
Print Spooler 服务异常，以及驱动程序不匹配。

三、网络连通性检查
确认电脑能够访问本地网络，检查网线或无线网络状态；不要在演示环境记录真实企业网络参数。

四、打印机 IP 和端口检查
使用文档示例地址 192.0.2.10 说明 ping 与 Test-NetConnection 的检查方法；
该地址仅供文档演示。核对 Windows 打印机端口与设备配置是否一致。

五、Windows 打印队列检查
打开“设置 → 蓝牙和设备 → 打印机和扫描仪”，选择目标打印机并打开打印队列，
确认没有暂停任务；必要时取消无效任务后重新提交一次测试页。

六、Print Spooler 服务检查
打开“服务”，找到 Print Spooler（打印后台处理程序），确认服务处于正在运行状态。
若服务异常，记录现象并按获批的运维流程处理。

七、驱动程序检查
确认驱动型号、系统架构和版本匹配。只从设备厂商官网或企业批准的软件源获取驱动，不使用未知来源安装包。

八、修复结果验证
重新打印测试页，确认任务进入队列、设备出纸、内容完整，并记录已执行的检查步骤和结果。

九、升级处理条件
设备持续离线、网络端口不可达、服务反复停止、驱动安装需要管理员权限，
或问题影响多名用户时，停止重复操作并升级给 IT 支持人员。"""

DEMO_SUBMIT_IDEMPOTENCY_KEY = "local-demo-data-01-submit-v1"
DEMO_APPROVE_IDEMPOTENCY_KEY = "local-demo-data-01-approve-publish-v1"


class Command(BaseCommand):
    help = "仅在 opsai-local-demo 隔离环境中幂等创建并正式发布首篇演示知识。"

    def handle(self, *args, **options):
        self._verify_isolated_environment()
        created = False
        try:
            with transaction.atomic():
                users = self._ensure_demo_identities()
                editor = users["dev_editor"]
                reviewer = users["dev_reviewer"]
                matches = list(
                    Article.objects.filter(title=DEMO_TITLE)
                    .select_related(
                        "space",
                        "category",
                        "owner",
                        "current_published_version",
                        "latest_working_version",
                    )
                    .order_by("pk")[:2]
                )
                if len(matches) > 1:
                    raise CommandError("演示文章标题存在多条记录，拒绝自动选择或覆盖。")
                if matches:
                    space = KnowledgeSpace.objects.get(code=DEMO_SPACE_CODE)
                    content_group = UserGroup.objects.get(name=DEMO_GROUP_NAME)
                    self._validate_completed_demo(
                        article=matches[0],
                        editor=editor,
                        reviewer=reviewer,
                        content_group=content_group,
                    )
                else:
                    call_command("seed_demo_data", verbosity=0, stdout=self.stdout)
                    space = KnowledgeSpace.objects.get(code=DEMO_SPACE_CODE)
                    category = Category.objects.get(space=space, code=DEMO_CATEGORY_CODE)
                    content_group = UserGroup.objects.get(name=DEMO_GROUP_NAME)
                    self._assign_empty_demo_space_to_editor(
                        space=space,
                        editor=editor,
                        expected_owner=users["dev_knowledge_admin"],
                    )
                    self._ensure_reviewer_scope(reviewer=reviewer, space=space)
                    self._create_and_publish_demo(
                        editor=editor,
                        reviewer=reviewer,
                        space=space,
                        category=category,
                        content_group=content_group,
                    )
                    created = True
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                "演示文章初始化失败，全部本轮数据库写入已整体回滚；"
                "未覆盖既有业务记录，请在隔离环境中检查异常链。"
            ) from exc

        action = "created: 1; existing: 0" if created else "created: 0; existing: 1"
        self.stdout.write(self.style.SUCCESS(f"LOCAL-DEMO-DATA-01 完成：{action}; conflict: 0"))

    @staticmethod
    def _verify_isolated_environment() -> dict[str, str]:
        """同时核验运行模式、Compose 标识、配置身份与数据库真实身份。"""
        if not settings.DEBUG:
            raise CommandError("拒绝执行：演示初始化要求 DEBUG=True 的本地开发运行模式。")
        if not settings.DEV_LOGIN_ENABLED:
            raise CommandError("拒绝执行：演示初始化要求显式启用本地开发登录。")
        if os.getenv("OPSAI_LOCAL_DEMO", "").strip().lower() != "true":
            raise CommandError("拒绝执行：缺少有效的独立演示环境标识。")
        if os.getenv("OPSAI_LOCAL_DEMO_PROJECT") != EXPECTED_PROJECT:
            raise CommandError("拒绝执行：Compose 项目标识不是 opsai-local-demo。")
        if os.getenv("OPSAI_LOCAL_DEMO_INSTANCE") != EXPECTED_INSTANCE:
            raise CommandError("拒绝执行：演示实例标识不匹配。")
        if os.getenv("OPSAI_LOCAL_DEMO_AUTHORIZED_HEAD") != AUTHORIZED_BASE_HEAD:
            raise CommandError("拒绝执行：演示环境授权基线标识不匹配。")

        database = settings.DATABASES["default"]
        if database.get("ENGINE") != "django.db.backends.postgresql":
            raise CommandError("拒绝执行：演示初始化只允许使用独立 PostgreSQL 数据库。")
        if database.get("NAME") != EXPECTED_DATABASE:
            raise CommandError("拒绝执行：目标数据库名称不是 opsai_local_demo。")
        if database.get("HOST") != EXPECTED_DATABASE_HOST or str(database.get("PORT")) != "5432":
            raise CommandError("拒绝执行：数据库连接未指向演示 Compose 内部 db:5432。")
        if Path(settings.BASE_DIR, ".env").exists():
            raise CommandError("拒绝执行：镜像中存在仓库根 .env，无法证明配置隔离。")
        if connection.vendor != "postgresql":
            raise CommandError("拒绝执行：当前数据库连接不是 PostgreSQL。")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), current_user, COALESCE(inet_server_addr()::text, '')"
            )
            actual_database, actual_user, server_address = cursor.fetchone()

        if actual_database != EXPECTED_DATABASE:
            raise CommandError("拒绝执行：数据库实际身份与演示数据库配置不一致。")
        if actual_user != database.get("USER"):
            raise CommandError("拒绝执行：数据库实际连接身份与演示配置不一致。")
        if not server_address:
            raise CommandError("拒绝执行：无法确认演示 PostgreSQL 服务地址。")
        return {
            "database": actual_database,
            "user": actual_user,
            "server": server_address,
        }

    def _ensure_demo_identities(self):
        """仅在四个固定开发用户名全部不存在时调用既有安全创建命令。"""
        user_model = get_user_model()
        existing = {
            identity.username: user_model.objects.filter(username=identity.username).first()
            for identity in DEV_IDENTITIES
        }
        present = [username for username, user in existing.items() if user is not None]
        if present and len(present) != len(DEV_IDENTITIES):
            raise CommandError("固定演示身份仅部分存在，拒绝补写或覆盖，请人工核验隔离数据库。")
        if not present:
            call_command("create_dev_users", verbosity=0, stdout=self.stdout)
            existing = {
                identity.username: user_model.objects.get(username=identity.username)
                for identity in DEV_IDENTITIES
            }

        conflicts = []
        for identity in DEV_IDENTITIES:
            user = existing[identity.username]
            reason = dev_user_deviation(user, identity)
            if reason:
                conflicts.append(f"{identity.username}（{reason}）")
        if conflicts:
            raise CommandError("固定演示身份不符合安全定义，拒绝自动修复：" + "、".join(conflicts))
        return existing

    @staticmethod
    def _assign_empty_demo_space_to_editor(*, space, editor, expected_owner):
        """首次初始化时把旧 DEMO 空间交给正式执行创建动作的编辑者。"""
        if space.owner_id == editor.pk:
            return
        if space.owner_id != expected_owner.pk or Article.objects.filter(space=space).exists():
            raise CommandError("演示空间负责人或既有文章与初始化合同不符，拒绝覆盖。")
        space.owner = editor
        space.full_clean()
        space.save(update_fields=("owner", "updated_at"))

    @staticmethod
    def _ensure_reviewer_scope(*, reviewer, space):
        scope = ReviewerSpaceScope.objects.filter(reviewer=reviewer, space=space).first()
        if scope is not None:
            if not scope.is_active:
                raise CommandError("既有演示审核范围已停用，拒绝自动重新激活。")
            return scope
        scope = ReviewerSpaceScope(reviewer=reviewer, space=space, is_active=True)
        scope.full_clean()
        scope.save(force_insert=True)
        return scope

    @staticmethod
    def _create_and_publish_demo(*, editor, reviewer, space, category, content_group):
        article, initial_draft = create_article(
            actor=editor,
            space=space,
            category=category,
            article_type=ArticleType.SOP,
            title=DEMO_TITLE,
            summary=DEMO_SUMMARY,
            applicable_scope={
                "classification": "DEMO",
                "environment": "isolated-local-demo",
                "platform": "Windows 10/11",
            },
            body_text=DEMO_INITIAL_BODY,
            change_summary="【DEMO】创建演示文章初始草稿",
            review_due_at=timezone.now() + timedelta(days=180),
            owner=editor,
            audience_policy=AudiencePolicy.RESTRICTED,
        )

        audience = ArticleAudience(
            article=article,
            audience_type=AudienceType.USER_GROUP,
            effect=AudienceEffect.ALLOW,
            user_group=content_group,
            created_by=editor,
        )
        audience.full_clean()
        audience.save(force_insert=True)

        _saved_version, review_draft = manual_save_draft(
            actor=editor,
            article=article,
            draft_id=initial_draft.pk,
            expected_lock_version=initial_draft.lock_version,
            title=DEMO_TITLE,
            summary=DEMO_SUMMARY,
            applicable_scope={
                "classification": "DEMO",
                "environment": "isolated-local-demo",
                "platform": "Windows 10/11",
            },
            body_text=DEMO_BODY_TEXT,
            change_summary="【DEMO】补全网络打印机故障排查九步 SOP",
        )
        submitted = submit_article_for_review(
            actor=editor,
            kb_no=article.kb_no,
            draft_id=review_draft.pk,
            expected_lock_version=review_draft.lock_version,
            idempotency_key=DEMO_SUBMIT_IDEMPOTENCY_KEY,
        )
        approve_and_publish_article_version(
            actor=reviewer,
            version_id=submitted.version_id,
            comment="【DEMO】内容与受众范围核验通过，批准用于本地演示。",
            idempotency_key=DEMO_APPROVE_IDEMPOTENCY_KEY,
        )

    @staticmethod
    def _validate_completed_demo(*, article, editor, reviewer, content_group):
        """幂等重跑只接受完整、未漂移的服务链结果，绝不静默修复。"""
        conflicts = []
        expected_fields = {
            "space.code": (article.space.code, DEMO_SPACE_CODE),
            "space.owner": (article.space.owner_id, editor.pk),
            "category.code": (article.category.code, DEMO_CATEGORY_CODE),
            "owner": (article.owner_id, editor.pk),
            "article_type": (article.article_type, ArticleType.SOP),
            "audience_policy": (article.audience_policy, AudiencePolicy.RESTRICTED),
            "article_status": (article.article_status, ArticleStatus.ACTIVE),
        }
        for label, (actual, expected) in expected_fields.items():
            if actual != expected:
                conflicts.append(label)

        versions = list(ArticleVersion.objects.filter(article=article).order_by("version_no"))
        if [version.status for version in versions] != [
            VersionStatus.SAVED,
            VersionStatus.PUBLISHED,
            VersionStatus.DRAFT,
        ]:
            conflicts.append("versions")
        if (
            article.current_published_version_id is None
            or article.latest_working_version_id is None
        ):
            conflicts.append("version pointers")
        else:
            published = article.current_published_version
            successor = article.latest_working_version
            if (
                published.status != VersionStatus.PUBLISHED
                or published.title != DEMO_TITLE
                or published.summary != DEMO_SUMMARY
                or published.body_plaintext != DEMO_BODY_TEXT
                or published.submitted_by_id != editor.pk
            ):
                conflicts.append("published snapshot")
            if successor.status != VersionStatus.DRAFT:
                conflicts.append("successor draft")

        audiences = list(ArticleAudience.objects.filter(article=article))
        if len(audiences) != 1 or not (
            audiences[0].audience_type == AudienceType.USER_GROUP
            and audiences[0].effect == AudienceEffect.ALLOW
            and audiences[0].user_group_id == content_group.pk
        ):
            conflicts.append("audience")

        if not ReviewerSpaceScope.objects.filter(
            reviewer=reviewer,
            space=article.space,
            is_active=True,
        ).exists():
            conflicts.append("reviewer scope")

        reviews = list(
            ReviewRecord.objects.filter(article_version_id=article.current_published_version_id)
        )
        if len(reviews) != 1 or not (
            reviews[0].reviewer_id == reviewer.pk and reviews[0].decision == ReviewDecision.APPROVED
        ):
            conflicts.append("review")

        records = list(
            WorkflowIdempotencyRecord.objects.filter(
                key__in=(DEMO_SUBMIT_IDEMPOTENCY_KEY, DEMO_APPROVE_IDEMPOTENCY_KEY)
            )
        )
        if len(records) != 2 or any(
            record.status != IdempotencyStatus.COMPLETED for record in records
        ):
            conflicts.append("idempotency")

        article_events = [
            event
            for event in WorkflowOutboxEvent.objects.all()
            if str(event.payload.get("article_id")) == str(article.pk)
        ]
        if len(article_events) != 2 or any(
            event.status != WorkflowOutboxStatus.PENDING
            or event.attempt_count != 0
            or event.sent_at is not None
            for event in article_events
        ):
            conflicts.append("outbox")
        if AuditEvent.objects.filter(article=article).count() != 2:
            conflicts.append("audit")

        if conflicts:
            raise CommandError(
                "同名演示文章已存在但完整性校验失败，拒绝覆盖：" + ", ".join(conflicts)
            )
