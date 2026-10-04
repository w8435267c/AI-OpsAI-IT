"""正式员工搜索只读入口。"""

from __future__ import annotations

from datetime import datetime

from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When

from apps.accounts.models import User
from apps.knowledge.models import Article
from apps.knowledge.readers import employee_visible_articles


def search_employee_articles(
    user: User,
    query: str | None,
    *,
    base: QuerySet[Article] | None = None,
    now: datetime | None = None,
) -> QuerySet[Article]:
    """在当前员工可见的正式知识中搜索，并返回可继续分页的 QuerySet。

    V1 仅匹配当前正式发布版本的标题、摘要和正文纯文本。权限过滤始终先于
    搜索、排序、统计和后续分页；空搜索词不会退化为“显示全部知识”。
    """
    visible = employee_visible_articles(user, base=base, now=now)
    if not isinstance(query, str):
        return visible.none()

    normalized_query = query.strip()
    if not normalized_query:
        return visible.none()

    title_match = Q(current_published_version__title__icontains=normalized_query)
    summary_match = Q(current_published_version__summary__icontains=normalized_query)
    body_match = Q(current_published_version__body_plaintext__icontains=normalized_query)

    return (
        visible.filter(title_match | summary_match | body_match)
        .alias(
            _search_match_priority=Case(
                When(title_match, then=Value(0)),
                When(summary_match, then=Value(1)),
                When(body_match, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by(
            "_search_match_priority",
            F("current_published_version__published_at").desc(nulls_last=True),
            F("updated_at").desc(nulls_last=True),
            "pk",
        )
    )
