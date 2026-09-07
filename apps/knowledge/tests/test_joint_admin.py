"""真实 Article Admin POST：权限、最终受众状态与事务回滚。"""

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import Client

from apps.accounts.models import User
from apps.accounts.tests.admin_helpers import build_change_post_data
from apps.knowledge.models import Article, ArticleAudience, AudiencePolicy, AudienceType
from apps.knowledge.tests.test_selectors import _add_audience, _mk_article, _mk_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    user = User.objects.create_superuser(username="joint-admin")
    client = Client()
    client.force_login(user)
    article = _mk_article()
    rule = _add_audience(article, AudienceType.USER, user=_mk_user())
    return user, client, article, rule


def payload(user, article, **overrides):
    return build_change_post_data(admin.site._registry[Article], user, article, **overrides)


def post(client, article, data):
    return client.post(f"/admin/knowledge/article/{article.pk}/change/", data)


def errors(response):
    return [response.context["adminform"].form.errors] + [
        (item.formset.errors, item.formset.non_form_errors())
        for item in response.context["inline_admin_formsets"]
    ]


@pytest.mark.parametrize("action", ["delete", "adjust", "replace"])
def test_joint_final_state_valid(setup, action):
    user, client, article, rule = setup
    data = payload(user, article, audience_policy=AudiencePolicy.ALL_EMPLOYEES)
    if action == "adjust":
        data.update(
            {"audience_rules-0-audience_type": "all_employees", "audience_rules-0-user": ""}
        )
    else:
        data["audience_rules-0-DELETE"] = "on"
    if action == "replace":
        data.update(
            {
                "audience_rules-TOTAL_FORMS": "2",
                "audience_rules-1-article": str(article.pk),
                "audience_rules-1-audience_type": "all_employees",
                "audience_rules-1-effect": "allow",
                "audience_rules-1-created_by": str(user.pk),
            }
        )
    response = post(client, article, data)
    assert response.status_code == 302, errors(response)
    article.refresh_from_db()
    assert article.audience_policy == AudiencePolicy.ALL_EMPLOYEES
    assert article.audience_rules.count() == (0 if action == "delete" else 1)


def test_delete_and_recreate_same_unique_key(setup):
    user, client, article, rule = setup
    data = payload(user, article)
    data.update(
        {
            "audience_rules-TOTAL_FORMS": "2",
            "audience_rules-0-DELETE": "on",
            "audience_rules-1-article": str(article.pk),
            "audience_rules-1-audience_type": "user",
            "audience_rules-1-effect": "allow",
            "audience_rules-1-user": str(rule.user_id),
            "audience_rules-1-created_by": str(user.pk),
        }
    )
    response = post(client, article, data)
    assert response.status_code == 302, errors(response)
    assert article.audience_rules.count() == 1
    assert not ArticleAudience.objects.filter(pk=rule.pk).exists()


@pytest.mark.parametrize("action", ["unchanged", "invalid_new", "omit_existing"])
def test_invalid_final_state_no_partial_save(setup, action):
    user, client, article, rule = setup
    original_title = article.title
    data = payload(user, article, audience_policy="all_employees", title="不得保存")
    if action == "invalid_new":
        data.update(
            {
                "audience_rules-0-DELETE": "on",
                "audience_rules-TOTAL_FORMS": "2",
                "audience_rules-1-article": str(article.pk),
                "audience_rules-1-audience_type": "user",
                "audience_rules-1-effect": "allow",
                "audience_rules-1-user": str(user.pk),
                "audience_rules-1-created_by": str(user.pk),
            }
        )
    if action == "omit_existing":
        data.update({"audience_rules-TOTAL_FORMS": "0", "audience_rules-INITIAL_FORMS": "0"})
    assert post(client, article, data).status_code == 200
    article.refresh_from_db()
    assert article.audience_policy == "restricted" and article.title == original_title
    assert ArticleAudience.objects.filter(pk=rule.pk).exists()


def test_save_failure_rolls_back_parent_and_deleted_rule(setup):
    user, client, article, rule = setup
    data = payload(user, article, title="不得部分保存")
    data.update(
        {
            "audience_rules-0-DELETE": "on",
            "audience_rules-TOTAL_FORMS": "2",
            "audience_rules-1-article": str(article.pk),
            "audience_rules-1-audience_type": "user",
            "audience_rules-1-effect": "deny",
            "audience_rules-1-user": str(user.pk),
            "audience_rules-1-created_by": str(user.pk),
        }
    )
    with patch.object(ArticleAudience, "save", side_effect=RuntimeError("模拟保存失败")):
        with pytest.raises(RuntimeError, match="模拟保存失败"):
            post(client, article, data)
    article.refresh_from_db()
    assert article.title != "不得部分保存"
    assert ArticleAudience.objects.filter(pk=rule.pk).exists()


@pytest.mark.parametrize("operation", ["add", "change", "delete"])
def test_missing_audience_permission_cannot_forge(setup, operation):
    root, client, article, rule = setup
    user = _mk_user(is_staff=True)
    permissions = ["change_article", "view_articleaudience"]
    user.user_permissions.set(
        Permission.objects.filter(content_type__app_label="knowledge", codename__in=permissions)
    )
    client.force_login(user)
    # 使用超管的完整表单构造攻击输入，不能通过界面字段缺失让测试自动避开攻击。
    data = payload(root, article, title="不得保存")
    if operation == "change":
        data["audience_rules-0-effect"] = "deny"
    elif operation == "delete":
        data["audience_rules-0-DELETE"] = "on"
    else:
        data.update(
            {
                "audience_rules-TOTAL_FORMS": "2",
                "audience_rules-1-article": str(article.pk),
                "audience_rules-1-audience_type": "user",
                "audience_rules-1-effect": "deny",
                "audience_rules-1-user": str(root.pk),
                "audience_rules-1-created_by": str(root.pk),
            }
        )
    response = post(client, article, data)
    assert response.status_code in (200, 403)
    article.refresh_from_db()
    rule.refresh_from_db()
    assert article.title != "不得保存" and rule.effect == "allow"
    assert article.audience_rules.count() == 1


def test_no_audience_permissions_cannot_skip_model_validation(setup):
    root, client, article, rule = setup
    user = _mk_user(is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="knowledge", codename="change_article")
    )
    client.force_login(user)
    data = payload(root, article, audience_policy="all_employees")
    data["skip_audience_validation"] = "true"
    assert post(client, article, data).status_code == 200
    article.refresh_from_db()
    assert article.audience_policy == "restricted"


def test_change_and_add_permissions_do_not_grant_delete(setup):
    root, client, article, rule = setup
    user = _mk_user(is_staff=True)
    user.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label="knowledge",
            codename__in=[
                "change_article",
                "view_articleaudience",
                "change_articleaudience",
                "add_articleaudience",
            ],
        )
    )
    client.force_login(user)
    data = payload(root, article, audience_policy="all_employees")
    data["audience_rules-0-DELETE"] = "on"
    assert post(client, article, data).status_code == 200
    rule.refresh_from_db()
    data = payload(root, article, audience_policy="all_employees")
    data.update({"audience_rules-0-audience_type": "all_employees", "audience_rules-0-user": ""})
    response = post(client, article, data)
    assert response.status_code == 302, errors(response)


def test_duplicate_new_rule_rejected_without_parent_save(setup):
    user, client, article, rule = setup
    data = payload(user, article, title="不得保存重复")
    data.update(
        {
            "audience_rules-TOTAL_FORMS": "2",
            "audience_rules-1-article": str(article.pk),
            "audience_rules-1-audience_type": "user",
            "audience_rules-1-effect": "allow",
            "audience_rules-1-user": str(rule.user_id),
            "audience_rules-1-created_by": str(user.pk),
        }
    )
    assert post(client, article, data).status_code == 200
    article.refresh_from_db()
    assert article.title != "不得保存重复"
    assert article.audience_rules.count() == 1


@pytest.mark.parametrize("policy", ["all_employees", "it_only", "restricted"])
def test_joint_deny_and_unchanged_rule_valid(setup, policy):
    user, client, article, rule = setup
    # 设置既有合法 deny，以便验证未变化的行也按新的文章策略校验。
    rule.effect = "deny"
    rule.save()
    data = payload(user, article, audience_policy=policy)
    response = post(client, article, data)
    assert response.status_code == 302, errors(response)
    assert ArticleAudience.objects.get(pk=rule.pk).effect == "deny"


def test_standalone_audience_admin_validation_preserved(setup):
    user, client, article, rule = setup
    Article.objects.filter(pk=article.pk).update(audience_policy="all_employees")
    data = {
        "article": str(article.pk),
        "audience_type": "user",
        "effect": "allow",
        "user": str(user.pk),
        "created_by": str(user.pk),
    }
    response = client.post("/admin/knowledge/articleaudience/add/", data)
    assert response.status_code == 200
    assert "audience_type" in response.context["adminform"].form.errors
    assert article.audience_rules.count() == 1
