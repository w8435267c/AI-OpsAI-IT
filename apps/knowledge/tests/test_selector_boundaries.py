"""第 8C 发现的边界问题与第 8D 公开 base 契约回归。"""

import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.accounts.models import User, UserGroup, UserGroupMembership
from apps.knowledge.configuration import MAX_USER_GROUP_ID, parse_it_group_id
from apps.knowledge.models import Article, AudiencePolicy, AudienceType
from apps.knowledge.selectors import can_read_article, visible_articles
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user, _publish

INVALID_CONFIGS = [
    None,
    "",
    " ",
    "abc",
    "²",
    "9" * 5000,
    "0",
    "-1",
    "1.5",
    str(2**63),
    2**63,
    0,
    -1,
    True,
    1.2,
    [],
    " 1",
    "+1",
]


@pytest.mark.parametrize("value", INVALID_CONFIGS)
def test_invalid_configuration(value):
    assert parse_it_group_id(value) is None


@pytest.mark.parametrize("value", [1, "1", MAX_USER_GROUP_ID, str(MAX_USER_GROUP_ID)])
def test_positive_bigauto_boundaries(value):
    assert parse_it_group_id(value) == int(value)
    assert UserGroup._meta.pk.get_internal_type() == "BigAutoField"


@pytest.mark.parametrize("value", [None, " ", "abc", "²", "9" * 5000, str(2**63), "1"])
def test_real_base_settings_parser(value):
    # 运行真实设置文件；只屏蔽 dotenv 文件读取，不替换解析函数。
    with patch.dict(os.environ), patch("dotenv.load_dotenv", return_value=False):
        os.environ.pop("KNOWLEDGE_IT_USER_GROUP_ID", None)
        if value is not None:
            os.environ["KNOWLEDGE_IT_USER_GROUP_ID"] = value
        loaded = runpy.run_path(
            str(Path(__file__).resolve().parents[3] / "config/settings/base.py")
        )
        assert loaded["KNOWLEDGE_IT_USER_GROUP_ID"] == (1 if value == "1" else None)


@pytest.mark.django_db
@pytest.mark.parametrize("value", INVALID_CONFIGS + [MAX_USER_GROUP_ID])
def test_overridden_config_does_not_break_public_query(value):
    public, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
    private, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
    user = _mk_user()
    with override_settings(KNOWLEDGE_IT_USER_GROUP_ID=value):
        assert list(visible_articles(user)) == [public]
        assert not can_read_article(user, private)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["no_pk", "new_pk", "existing_pk", "loaded"])
def test_account_saved_state(kind):
    existing = _mk_user()
    user = {
        "no_pk": User(),
        "new_pk": User(pk=999999),
        "existing_pk": User(pk=existing.pk),
        "loaded": User.objects.get(pk=existing.pk),
    }[kind]
    article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
    assert visible_articles(user).exists() == (kind == "loaded")
    assert can_read_article(user, article) == (kind == "loaded")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ordering",
    [
        "title",
        "-title",
        "audience_rules__user__username",
        "-audience_rules__user__username",
        "space__name",
    ],
)
def test_duplicate_base_order_count_and_pages(ordering):
    user = _mk_user()
    a, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
    b, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
    outsider, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
    for article, name in ((a, "alpha"), (a, "zulu"), (b, "middle")):
        _add_audience(article, AudienceType.USER, user=_mk_user(username=name))
    base = Article.objects.filter(pk__in=[a.pk, b.pk], audience_rules__effect="allow").order_by(
        ordering
    )
    expected = list(dict.fromkeys(base.values_list("pk", flat=True)))
    result = visible_articles(user, base=base)
    assert list(result.values_list("pk", flat=True)) == expected
    assert result.count() == 2
    assert list(result[:1]) + list(result[1:2]) == list(result)
    assert outsider not in result
    assert all(can_read_article(user, article) for article in result)
    assert list(visible_articles(user, base=base.reverse()).values_list("pk", flat=True)) == list(
        dict.fromkeys(base.reverse().values_list("pk", flat=True))
    )


@pytest.mark.django_db
def test_special_base_rejected_explicitly():
    from django.db.models import Count

    user = _mk_user()
    for base in (
        Article.objects.all()[:1],
        Article.objects.values("pk"),
        Article.objects.annotate(n=Count("audience_rules")),
        Article.objects.order_by("?"),
    ):
        with pytest.raises(ValueError):
            visible_articles(user, base=base)


@pytest.mark.django_db
@pytest.mark.parametrize("policy", ["all_employees", "it_only", "restricted"])
@pytest.mark.parametrize("target", ["user", "user_group"])
def test_user_and_group_deny_priority(policy, target):
    user = _mk_user()
    group = UserGroup.objects.create(name="回归内容组")
    UserGroupMembership.objects.create(user=user, user_group=group)
    article, _ = _publish(_mk_article(policy=policy))
    _add_audience(article, "user", user=user)
    _add_audience(
        article, target, "deny", **({"user": user} if target == "user" else {"user_group": group})
    )
    with override_settings(KNOWLEDGE_IT_USER_GROUP_ID=group.pk):
        assert not can_read_article(user, article)
        assert not visible_articles(user).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("effect", ["allow", "deny"])
def test_inactive_group_allow_and_deny(effect):
    user = _mk_user()
    group = UserGroup.objects.create(name="停用组", is_active=False)
    UserGroupMembership.objects.create(user=user, user_group=group)
    article, _ = _publish(
        _mk_article(policy="restricted" if effect == "allow" else "all_employees")
    )
    _add_audience(article, "user_group", effect, user_group=group)
    assert can_read_article(user, article) == (effect == "deny")


@pytest.mark.django_db
def test_distinct_base_multiple_order_columns():
    user = _mk_user()
    article, _ = _publish(_mk_article(policy="all_employees"))
    _add_audience(article, "user", user=user)
    _add_audience(article, "user", user=_mk_user())
    base = (
        Article.objects.filter(audience_rules__effect="allow")
        .order_by("title", "audience_rules__user__username")
        .distinct()
    )
    assert list(visible_articles(user, base=base)) == [article]
