"""知识内容受众 Selector：决定当前用户可见哪些已发布文章。

依据：PRD V1.1A 第 4.2 节“权限设计原则”、第 9.3 节“搜索与权限规则”，
以及 docs/07-ADR/0001-内容受众选择器权限语义.md。

本模块只实现“员工阅读路径”的内容受众判定，返回可继续过滤、排序、计数和
分页的 Article QuerySet，或单篇是否可见的布尔值；不负责 HTTP 403/404、搜索、
附件或管理端权限。系统操作角色（Django Group/Permission）与本模块无关，
staff / superuser / 编辑员 / 审核员 / 知识管理员 / 作者 / 空间负责人均不绕过
受众检查。

判定顺序：
1. 账号门槛：user 为 None、匿名、未保存、is_active=False 或 account_status
   非 active → 直接空集 / False，不进入受众计算。
2. 文章策略决定允许范围：
   - all_employees：所有满足账号门槛的用户；
   - it_only：满足账号门槛且属于绑定的 IT 内容用户组
     （KNOWLEDGE_IT_USER_GROUP_ID 指向的启用用户组）；
   - restricted：命中显式 allow 的部门 / 内容用户组 / 用户；
   - 未识别策略：放行失败（无人可见）。
3. 拒绝优先：任一匹配的 department / user_group / user deny 覆盖允许范围，
   对三种策略一致生效。
4. 内容状态：空间启用、文章 active、存在已发布且属于本文章的当前发布版本、
   生效时间已到。
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Exists, F, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from apps.accounts.models import AccountStatus, User, UserDepartment, UserGroupMembership
from apps.knowledge.configuration import parse_it_group_id
from apps.knowledge.models import (
    Article,
    ArticleAudience,
    ArticleStatus,
    AudienceEffect,
    AudiencePolicy,
    AudienceType,
    VersionStatus,
)


def _user_account_allowed(user) -> bool:
    """账号门槛：匿名、未保存、禁用或非正常状态一律不进入受众计算。"""
    if not isinstance(user, User) or not user.is_authenticated:
        return False
    if not user.pk or user._state.adding:
        return False
    if not user.is_active:
        return False
    if user.account_status != AccountStatus.ACTIVE:
        return False
    return True


def _active_department_ids(user, now):
    """用户当前有效的启用部门主键子查询（不物化，供 __in 内联）。"""
    return (
        UserDepartment.objects.filter(
            user=user,
            department__is_active=True,
        )
        .filter(
            Q(effective_at__isnull=True) | Q(effective_at__lte=now),
            Q(expired_at__isnull=True) | Q(expired_at__gt=now),
        )
        .values_list("department_id", flat=True)
    )


def _active_group_ids(user):
    """用户当前所属的启用内容用户组主键子查询（不物化，供 __in 内联）。"""
    return UserGroupMembership.objects.filter(
        user=user,
        user_group__is_active=True,
    ).values_list("user_group_id", flat=True)


def _configured_it_group_id():
    """读取“仅 IT”绑定的内容用户组主键；未配置或无法解析为整数返回 None。"""
    return parse_it_group_id(getattr(settings, "KNOWLEDGE_IT_USER_GROUP_ID", None))


def _unique_article_base(base):
    """将 base 的范围与排序投影到唯一文章；详见 ADR-0001 的公开契约。"""
    if base is None:
        return Article.objects.order_by("-updated_at", "pk")
    if not isinstance(base, QuerySet) or base.model is not Article:
        raise ValueError("base 必须是 Article QuerySet。")
    query = base.query
    if (
        base._fields is not None
        or query.is_sliced
        or query.combinator
        or query.annotations
        or query.extra
        or query.select_for_update
        or query.distinct_fields
        or query.deferred_loading[0]
    ):
        raise ValueError("base 不支持投影、预先切片、集合运算、注解、额外 SQL、锁或延迟字段。")
    ordering = query.order_by or (Article._meta.ordering if query.default_ordering else ())
    normalized = []
    for term in ordering:
        if not isinstance(term, str) or term == "?":
            raise ValueError("base 排序仅支持确定的模型字段路径，不支持随机或表达式排序。")
        descending = term.startswith("-")
        parts = term.lstrip("-").split("__")
        model = Article
        for index, part in enumerate(parts):
            field = model._meta.pk if part == "pk" else model._meta.get_field(part)
            if index < len(parts) - 1:
                if not field.is_relation:
                    raise ValueError("base 排序必须使用模型字段路径。")
                model = field.related_model
            elif field.is_relation:
                if not field.concrete:
                    raise ValueError("关联排序请明确指定末级字段。")
                if part == field.name and field.related_model._meta.ordering:
                    raise ValueError("关联模型有默认排序，请显式指定关联排序字段。")
                parts[index] = field.attname
        if not query.standard_ordering:
            descending = not descending
        normalized.append(("-" if descending else "") + "__".join(parts))
    qs = Article.objects.using(base.db).filter(pk__in=base.order_by().values("pk"))
    if base.query.select_related:
        from copy import deepcopy

        qs.query.select_related = deepcopy(base.query.select_related)
    if base._prefetch_related_lookups:
        qs = qs.prefetch_related(*base._prefetch_related_lookups)
    # 每篇文章取 base 按完整排序元组排出的首行；所有排序值来自同一行。
    # 外层不连接一对多表，因此 count/分页不受关联行数影响。
    ordered_rows = base.filter(pk=OuterRef("pk")).order_by(*normalized)
    ordered_rows.query.distinct = False
    ordered_rows.query.standard_ordering = True
    result_order = []
    for index, term in enumerate(normalized):
        alias = f"_audience_order_{index}"
        qs = qs.alias(**{alias: Subquery(ordered_rows.values(term.lstrip("-"))[:1])})
        result_order.append(("-" if term.startswith("-") else "") + alias)
    return qs.order_by(*result_order, "pk")


def _is_it_staff(user) -> bool:
    """用户是否属于绑定的、启用的 IT 内容用户组。

    配置缺失、无效、组不存在或停用、用户非成员均返回 False；绝不按显示名称、
    部门名、角色名、is_staff 或 is_superuser 猜测 IT 身份。
    """
    group_id = _configured_it_group_id()
    if group_id is None:
        return False
    return UserGroupMembership.objects.filter(
        user=user,
        user_group_id=group_id,
        user_group__is_active=True,
    ).exists()


def _restricted_allow_exists(dept_ids, group_ids, user_pk):
    """restricted 策略下命中任一 allow 规则的子查询（EXISTS 取或）。"""
    return (
        Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.DEPARTMENT,
                effect=AudienceEffect.ALLOW,
                department_id__in=dept_ids,
            )
        )
        | Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.USER_GROUP,
                effect=AudienceEffect.ALLOW,
                user_group_id__in=group_ids,
            )
        )
        | Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.USER,
                effect=AudienceEffect.ALLOW,
                user_id=user_pk,
            )
        )
    )


def _deny_exists(dept_ids, group_ids, user_pk):
    """命中任一 deny 规则的子查询（EXISTS 取或），对三种策略一致生效。"""
    return (
        Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.DEPARTMENT,
                effect=AudienceEffect.DENY,
                department_id__in=dept_ids,
            )
        )
        | Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.USER_GROUP,
                effect=AudienceEffect.DENY,
                user_group_id__in=group_ids,
            )
        )
        | Exists(
            ArticleAudience.objects.filter(
                article=OuterRef("pk"),
                audience_type=AudienceType.USER,
                effect=AudienceEffect.DENY,
                user_id=user_pk,
            )
        )
    )


def _audience_eligible_articles(user, *, base=None, now=None):
    """只过滤业务可见性，不证明存在可读取的正式内容。

    返回账号、文章/空间状态、生效时间及受众规则允许的候选 QuerySet。
    调用方必须另行核验正式内容，不能将候选集作为完整授权结果。

    base 为可选的 Article QuerySet；传入时仅在其范围内进一步收紧，不丢弃其
    原过滤条件。user 不满足账号门槛时返回空集。
    """
    now = now or timezone.now()
    qs = _unique_article_base(base)

    if not _user_account_allowed(user):
        return qs.none()

    dept_ids = _active_department_ids(user, now)
    group_ids = _active_group_ids(user)
    is_it = _is_it_staff(user)

    qs = qs.filter(
        article_status=ArticleStatus.ACTIVE,
        space__is_active=True,
    ).filter(
        Q(effective_at__isnull=True) | Q(effective_at__lte=now),
    )

    # 允许范围只由文章策略决定；不一致的 allow 规则不参与、也不扩大范围。
    policy_allow_q = Q(audience_policy=AudiencePolicy.ALL_EMPLOYEES)
    if is_it:
        policy_allow_q |= Q(audience_policy=AudiencePolicy.IT_ONLY)
    policy_allow_q |= Q(audience_policy=AudiencePolicy.RESTRICTED) & _restricted_allow_exists(
        dept_ids, group_ids, user.pk
    )
    qs = qs.filter(policy_allow_q)

    # 拒绝优先：deny 对 all_employees / it_only / restricted 一致生效。
    qs = qs.exclude(_deny_exists(dept_ids, group_ids, user.pk))

    return qs


def visible_articles(user, *, base=None, now=None):
    """返回对 user 可见（业务可见且旧正式版本有效）的文章 QuerySet。

    base 和 now 沿用公共过滤契约；旧发布限制始终执行，不能由调用方关闭。
    """
    return _audience_eligible_articles(user, base=base, now=now).filter(
        current_published_version__isnull=False,
        current_published_version__status=VersionStatus.PUBLISHED,
        current_published_version__article_id=F("pk"),
    )


def can_read_article(user, article, *, now=None):
    """单篇是否可见；复用 visible_articles，按数据库当前记录判断。

    article 为 None、未保存或已删除返回 False；不依赖传入对象中过期的权限
    或状态字段。
    """
    if article is None or not getattr(article, "pk", None):
        return False
    return visible_articles(user, base=Article.objects.filter(pk=article.pk), now=now).exists()
