# ruff: noqa: E402
"""验证恢复库中的关键业务记录和关系；不写入任何数据。"""

from __future__ import annotations

import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from apps.accounts.models import User
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleVersion,
    FeedbackRecord,
    ReviewRecord,
)


def main() -> None:
    database_name = settings.DATABASES["default"]["NAME"]
    if os.environ.get("OPSAI_BACKUP_RESTORE_DRILL") != "true" or connection.vendor != "postgresql":
        raise CommandError("拒绝验证：仅允许隔离 PostgreSQL 恢复演练。")
    if not database_name.startswith("opsai_backup_restore_"):
        raise CommandError("拒绝验证：数据库名不属于本次隔离恢复演练。")

    article = Article.objects.select_related("current_published_version").get(kb_no="KB-900001")
    employee = User.objects.get(username="backup_restore_employee")
    version = article.current_published_version
    if version is None or version.article_id != article.pk:
        raise CommandError("恢复后的已发布版本指针缺失或不一致。")
    if not ArticleAudience.objects.filter(article=article, user=employee, effect="allow").exists():
        raise CommandError("恢复后的受众授权缺失。")
    if not ReviewRecord.objects.filter(article_version=version, decision="approved").exists():
        raise CommandError("恢复后的审核记录缺失。")
    if not FeedbackRecord.objects.filter(
        article=article, article_version=version, user=employee, outcome="resolved"
    ).exists():
        raise CommandError("恢复后的反馈与文章版本关联缺失。")
    print(
        json.dumps(
            {
                "database": database_name,
                "accounts_user": User.objects.count(),
                "kb_article": Article.objects.count(),
                "kb_article_version": ArticleVersion.objects.count(),
                "kb_review_record": ReviewRecord.objects.count(),
                "kb_article_audience": ArticleAudience.objects.count(),
                "kb_feedback_record": FeedbackRecord.objects.count(),
                "business_relationships": "PASS",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
