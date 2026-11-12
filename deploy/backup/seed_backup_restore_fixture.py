# ruff: noqa: E402
"""仅为 PILOT-BACKUP-RESTORE-01 的全新隔离 PostgreSQL 写入合成恢复夹具。"""

from __future__ import annotations

import json
import os
from datetime import timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleType,
    ArticleVersion,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    Category,
    FeedbackOutcome,
    FeedbackRecord,
    KnowledgeSpace,
    ReviewDecision,
    ReviewRecord,
    ReviewType,
    SpaceType,
    VersionStatus,
)


def _assert_isolated_database() -> None:
    if os.environ.get("OPSAI_BACKUP_RESTORE_DRILL") != "true":
        raise CommandError("拒绝写入：缺少隔离演练标识 OPSAI_BACKUP_RESTORE_DRILL=true。")
    if connection.vendor != "postgresql" or not settings.DATABASES["default"]["NAME"].startswith(
        "opsai_backup_restore_"
    ):
        raise CommandError("拒绝写入：目标必须是 opsai_backup_restore_ 前缀的 PostgreSQL 数据库。")


def main() -> None:
    _assert_isolated_database()
    if Article.objects.exists() or User.objects.exists():
        raise CommandError("拒绝写入：夹具数据库不是全新空库。")

    now = timezone.now()
    with transaction.atomic():
        employee = User.objects.create_user(
            username="backup_restore_employee", display_name="备份恢复合成员工"
        )
        owner = User.objects.create_user(username="backup_restore_owner")
        reviewer = User.objects.create_user(username="backup_restore_reviewer")
        space = KnowledgeSpace.objects.create(
            code="backup-restore-space",
            name="备份恢复演练空间",
            space_type=SpaceType.EMPLOYEE,
            owner=owner,
            default_audience_policy=AudiencePolicy.RESTRICTED,
        )
        category = Category.objects.create(
            space=space, code="backup-restore", name="备份恢复演练分类"
        )
        article = Article.objects.create(
            kb_no="KB-900001",
            title="备份恢复合成知识",
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.RESTRICTED,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=now + timedelta(days=180),
        )
        version = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status=VersionStatus.PUBLISHED,
            title=article.title,
            summary="用于 PostgreSQL 备份恢复一致性核验的合成数据。",
            body={"type": "doc", "content": [{"type": "paragraph", "text": "合成恢复正文"}]},
            body_plaintext="合成恢复正文",
            change_summary="创建恢复演练发布版本",
            created_by=owner,
            submitted_by=owner,
            submitted_at=now,
            published_at=now,
        )
        article.current_published_version = version
        article.save(update_fields=["current_published_version", "updated_at"])
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.USER,
            effect=AudienceEffect.ALLOW,
            user=employee,
            created_by=owner,
        )
        ReviewRecord.objects.create(
            article_version=version,
            review_type=ReviewType.CONTENT_REVIEW,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
            comment="合成演练审核通过。",
        )
        FeedbackRecord.objects.create(
            article=article,
            article_version=version,
            user=employee,
            outcome=FeedbackOutcome.RESOLVED,
        )

    print(
        json.dumps(
            {"fixture": "created", "database": settings.DATABASES["default"]["NAME"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
