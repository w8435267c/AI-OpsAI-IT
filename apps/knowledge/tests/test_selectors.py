"""内容受众 Selector 测试。

覆盖 docs/07-ADR/0001 与第 8B 步确认的判定语义：账号门槛、三种文章策略的
允许范围、拒绝优先、仅 IT 绑定、多部门并集 / 精确匹配、内容状态与时间边界、
写入一致性校验、去重与 list == single 一致性，以及代表性查询数证明。

测试环境默认 KNOWLEDGE_IT_USER_GROUP_ID=None（见 config/settings/test.py）；
仅 IT 相关测试通过 self.settings / override_settings 指定临时用户组主键。
"""

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import (
    AccountStatus,
    Department,
    User,
    UserDepartment,
    UserGroup,
    UserGroupMembership,
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
    SpaceType,
    VersionStatus,
)
from apps.knowledge.selectors import (
    _audience_eligible_articles,
    can_read_article,
    visible_articles,
)

_seq = {"user": 0, "space": 0, "category": 0, "kb": 0}


def _mk_user(**kwargs):
    _seq["user"] += 1
    kwargs.setdefault("username", f"seluser{_seq['user']}")
    return User.objects.create_user(**kwargs)


def _mk_space(**kwargs):
    _seq["space"] += 1
    owner = kwargs.pop("owner", None) or _mk_user()
    kwargs.setdefault("name", f"选择器空间{_seq['space']}")
    kwargs.setdefault("code", f"sel-space-{_seq['space']}")
    kwargs.setdefault("space_type", SpaceType.EMPLOYEE)
    return KnowledgeSpace.objects.create(owner=owner, **kwargs)


def _mk_category(space, **kwargs):
    _seq["category"] += 1
    kwargs.setdefault("name", f"选择器分类{_seq['category']}")
    kwargs.setdefault("code", f"sel-cat-{_seq['category']}")
    return Category.objects.create(space=space, **kwargs)


def _mk_article(policy=AudiencePolicy.RESTRICTED, *, space=None, category=None, **kwargs):
    space = space or _mk_space()
    category = category or _mk_category(space)
    owner = kwargs.pop("owner", None) or _mk_user()
    _seq["kb"] += 1
    kb_no = kwargs.pop("kb_no", None) or f"KB-9{_seq['kb']:05d}"
    review_due_at = kwargs.pop("review_due_at", None) or (timezone.now() + timedelta(days=30))
    return Article.objects.create(
        kb_no=kb_no,
        title=f"选择器文章{_seq['kb']}",
        space=space,
        category=category,
        article_type=ArticleType.GUIDE,
        audience_policy=policy,
        owner=owner,
        created_by=owner,
        updated_by=owner,
        review_due_at=review_due_at,
        **kwargs,
    )


def _publish(article, *, published_at=None):
    """为文章挂一个已发布版本并把 current_published_version 指过去。"""
    now = timezone.now()
    version = ArticleVersion.objects.create(
        article=article,
        version_no=1,
        status=VersionStatus.PUBLISHED,
        title=article.title,
        summary="摘要",
        change_summary="初始",
        created_by=article.owner,
        submitted_by=article.owner,
        submitted_at=now,
        published_at=published_at or now,
    )
    article.current_published_version = version
    article.save(update_fields=["current_published_version"])
    return article, version


def _add_audience(
    article,
    audience_type,
    effect=AudienceEffect.ALLOW,
    *,
    department=None,
    user_group=None,
    user=None,
):
    return ArticleAudience.objects.create(
        article=article,
        audience_type=audience_type,
        effect=effect,
        department=department,
        user_group=user_group,
        user=user,
        created_by=article.owner,
    )


class AccountGateTests(TestCase):
    """账号门槛：匿名 / 未保存 / 禁用 / 非正常状态一律空集。"""

    def setUp(self):
        self.article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

    def test_none_user_sees_nothing(self):
        self.assertEqual(list(visible_articles(None)), [])

    def test_anonymous_user_sees_nothing(self):
        anon = AnonymousUser()
        self.assertEqual(list(visible_articles(anon)), [])
        self.assertFalse(can_read_article(anon, self.article))

    def test_unsaved_user_sees_nothing(self):
        unsaved = User(username="sel_unsaved")
        self.assertEqual(list(visible_articles(unsaved)), [])
        self.assertFalse(can_read_article(unsaved, self.article))

    def test_disabled_user_sees_nothing(self):
        self.assertEqual(list(visible_articles(_mk_user(is_active=False))), [])

    def test_departed_user_sees_nothing(self):
        u = _mk_user(account_status=AccountStatus.DEPARTED)
        self.assertEqual(list(visible_articles(u)), [])

    def test_disabled_status_user_sees_nothing(self):
        u = _mk_user(account_status=AccountStatus.DISABLED)
        self.assertEqual(list(visible_articles(u)), [])

    def test_active_user_sees_all_employees_article(self):
        u = _mk_user()
        self.assertIn(self.article, visible_articles(u))
        self.assertTrue(can_read_article(u, self.article))


class PolicyAllowTests(TestCase):
    """三种文章策略的允许范围。"""

    def test_all_employees_visible_to_any_active_user(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        self.assertIn(article, visible_articles(_mk_user()))

    def test_restricted_with_department_allow(self):
        dept = Department.objects.create(name="IT 部")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertIn(article, visible_articles(u))

    def test_restricted_with_user_group_allow(self):
        group = UserGroup.objects.create(name="新员工")
        u = _mk_user()
        UserGroupMembership.objects.create(user=u, user_group=group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.USER_GROUP, user_group=group)
        self.assertIn(article, visible_articles(u))

    def test_restricted_with_user_allow(self):
        u = _mk_user()
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.USER, user=u)
        self.assertIn(article, visible_articles(u))

    def test_restricted_no_rule_invisible(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        self.assertNotIn(article, visible_articles(_mk_user()))

    def test_restricted_only_deny_invisible(self):
        dept = Department.objects.create(name="IT 部")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, effect=AudienceEffect.DENY, department=dept)
        self.assertNotIn(article, visible_articles(u))

    def test_unrecognized_policy_not_visible(self):
        # 未识别策略按失败关闭：不因 allow 规则或账号状态放行。
        article, _ = _publish(_mk_article(policy="bogus"))
        self.assertNotIn(article, visible_articles(_mk_user()))


class DenyOverrideTests(TestCase):
    """拒绝优先：deny 覆盖 allow / 全员 / 仅 IT。"""

    def test_deny_overrides_allow_same_article(self):
        dept = Department.objects.create(name="IT 部")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(
            article, AudienceType.DEPARTMENT, effect=AudienceEffect.ALLOW, department=dept
        )
        _add_audience(article, AudienceType.DEPARTMENT, effect=AudienceEffect.DENY, department=dept)
        self.assertNotIn(article, visible_articles(u))

    def test_deny_overrides_all_employees(self):
        dept = Department.objects.create(name="IT 部")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        _add_audience(article, AudienceType.DEPARTMENT, effect=AudienceEffect.DENY, department=dept)
        self.assertNotIn(article, visible_articles(u))
        # 未命中 deny 的其他用户仍可见
        self.assertIn(article, visible_articles(_mk_user()))


class ItGroupUnconfiguredTests(TestCase):
    """仅 IT 绑定缺省未配置：it_only 文章无人可见，且不影响其它策略。"""

    @override_settings(KNOWLEDGE_IT_USER_GROUP_ID=None)
    def test_it_only_invisible_when_unconfigured(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        self.assertNotIn(article, visible_articles(_mk_user()))

    @override_settings(KNOWLEDGE_IT_USER_GROUP_ID=None)
    def test_other_policies_still_work_when_unconfigured(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        self.assertIn(article, visible_articles(_mk_user()))

    @override_settings(KNOWLEDGE_IT_USER_GROUP_ID="not-an-int")
    def test_invalid_config_treated_as_unconfigured(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        self.assertNotIn(article, visible_articles(_mk_user()))


class ItGroupConfiguredTests(TestCase):
    """仅 IT 绑定生效时的判定：成员可见、非成员 / 停用 / 不存在组均不可见。"""

    def _group(self, *, is_active=True):
        return UserGroup.objects.create(name="IT 运维组", is_active=is_active)

    def _member(self, group):
        u = _mk_user()
        UserGroupMembership.objects.create(user=u, user_group=group)
        return u

    def test_it_only_visible_to_member(self):
        group = self._group()
        u = self._member(group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            self.assertIn(article, visible_articles(u))

    def test_it_only_invisible_to_non_member(self):
        group = self._group()
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            self.assertNotIn(article, visible_articles(_mk_user()))

    def test_it_only_invisible_when_group_disabled(self):
        group = self._group(is_active=False)
        u = self._member(group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            self.assertNotIn(article, visible_articles(u))

    def test_it_only_invisible_for_nonexistent_group_id(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=99999999):
            self.assertNotIn(article, visible_articles(_mk_user()))

    def test_member_removal_updates_result(self):
        group = self._group()
        u = _mk_user()
        membership = UserGroupMembership.objects.create(user=u, user_group=group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            self.assertIn(article, visible_articles(u))
            membership.delete()
            self.assertNotIn(article, visible_articles(u))

    def test_it_only_still_subject_to_deny(self):
        group = self._group()
        dept = Department.objects.create(name="测试部")
        u = self._member(group)
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.IT_ONLY))
        _add_audience(article, AudienceType.DEPARTMENT, effect=AudienceEffect.DENY, department=dept)
        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            self.assertNotIn(article, visible_articles(u))


class NoRoleBypassTests(TestCase):
    """staff / superuser / 作者不绕过员工阅读路径受众检查。"""

    def setUp(self):
        self.article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))

    def test_staff_user_does_not_bypass(self):
        self.assertNotIn(self.article, visible_articles(_mk_user(is_staff=True)))

    def test_superuser_does_not_bypass(self):
        u = _mk_user(is_staff=True, is_superuser=True)
        self.assertNotIn(self.article, visible_articles(u))

    def test_author_does_not_bypass(self):
        self.assertNotIn(self.article, visible_articles(self.article.owner))


class DepartmentTests(TestCase):
    """部门与成员关系：多部门并集、精确匹配、时间边界、停用不参与。"""

    def test_multi_department_union(self):
        dept_a = Department.objects.create(name="A")
        dept_b = Department.objects.create(name="B")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept_a)
        UserDepartment.objects.create(user=u, department=dept_b)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept_b)
        self.assertIn(article, visible_articles(u))

    def test_primary_department_not_special(self):
        dept_a = Department.objects.create(name="A")
        dept_b = Department.objects.create(name="B")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept_a, is_primary=True)
        UserDepartment.objects.create(user=u, department=dept_b, is_primary=False)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept_b)
        self.assertIn(article, visible_articles(u))

    def test_parent_child_not_inherited(self):
        parent = Department.objects.create(name="父部门")
        child = Department.objects.create(name="子部门", parent=parent)
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=child)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=parent)
        self.assertNotIn(article, visible_articles(u))

    def test_effective_at_null_visible(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        now = timezone.now()
        UserDepartment.objects.create(user=u, department=dept, effective_at=None)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertIn(article, visible_articles(u, now=now))

    def test_effective_at_future_not_visible(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        now = timezone.now()
        UserDepartment.objects.create(user=u, department=dept, effective_at=now + timedelta(days=1))
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertNotIn(article, visible_articles(u, now=now))

    def test_effective_at_exactly_now_visible(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        now = timezone.now()
        UserDepartment.objects.create(user=u, department=dept, effective_at=now)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertIn(article, visible_articles(u, now=now))

    def test_expired_at_past_not_visible(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        now = timezone.now()
        UserDepartment.objects.create(user=u, department=dept, expired_at=now - timedelta(days=1))
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertNotIn(article, visible_articles(u, now=now))

    def test_expired_at_exactly_now_not_visible(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        now = timezone.now()
        UserDepartment.objects.create(user=u, department=dept, expired_at=now)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertNotIn(article, visible_articles(u, now=now))

    def test_inactive_department_allow_not_matched(self):
        dept = Department.objects.create(name="A", is_active=False)
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertNotIn(article, visible_articles(u))

    def test_inactive_department_deny_not_applied(self):
        dept = Department.objects.create(name="A", is_active=False)
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        _add_audience(article, AudienceType.DEPARTMENT, effect=AudienceEffect.DENY, department=dept)
        self.assertIn(article, visible_articles(u))

    def test_inactive_group_not_matched(self):
        group = UserGroup.objects.create(name="G", is_active=False)
        u = _mk_user()
        UserGroupMembership.objects.create(user=u, user_group=group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.USER_GROUP, user_group=group)
        self.assertNotIn(article, visible_articles(u))


class ContentStatusTests(TestCase):
    """内容状态与时间边界：空间 / 文章 / 版本 / 生效时间。"""

    def test_space_inactive_excluded(self):
        space = _mk_space(is_active=False)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES, space=space))
        self.assertNotIn(article, visible_articles(_mk_user()))

    def test_article_offline_excluded(self):
        article, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                article_status=ArticleStatus.OFFLINE,
            )
        )
        self.assertNotIn(article, visible_articles(_mk_user()))

    def test_article_archived_excluded(self):
        article, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                article_status=ArticleStatus.ARCHIVED,
            )
        )
        self.assertNotIn(article, visible_articles(_mk_user()))

    def test_future_effective_at_excluded(self):
        now = timezone.now()
        article, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                effective_at=now + timedelta(days=1),
            )
        )
        self.assertNotIn(article, visible_articles(_mk_user(), now=now))

    def test_no_published_version_excluded(self):
        article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        user = _mk_user()
        self.assertIn(article, _audience_eligible_articles(user))
        self.assertNotIn(article, visible_articles(user))
        self.assertFalse(can_read_article(user, article))

    def test_wrong_version_status_excluded(self):
        article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        version = ArticleVersion.objects.create(
            article=article,
            version_no=1,
            status=VersionStatus.DRAFT,
            title="草稿标题",
            summary="摘要",
            change_summary="初始",
            created_by=article.owner,
        )
        article.current_published_version = version
        article.save(update_fields=["current_published_version"])
        user = _mk_user()
        self.assertIn(article, _audience_eligible_articles(user))
        self.assertNotIn(article, visible_articles(user))
        self.assertFalse(can_read_article(user, article))

    def test_pointer_to_other_article_excluded(self):
        article_a = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        article_b, version_b = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        article_a.current_published_version = version_b
        article_a.save(update_fields=["current_published_version"])
        u = _mk_user()
        self.assertIn(article_a, _audience_eligible_articles(u))
        self.assertNotIn(article_a, visible_articles(u))
        self.assertFalse(can_read_article(u, article_a))
        self.assertIn(article_b, visible_articles(u))

    def test_new_version_in_review_old_published_still_visible(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        ArticleVersion.objects.create(
            article=article,
            version_no=2,
            status=VersionStatus.IN_REVIEW,
            title="新标题",
            summary="新摘要",
            change_summary="修订",
            created_by=article.owner,
            submitted_by=article.owner,
            submitted_at=timezone.now(),
        )
        self.assertIn(article, visible_articles(_mk_user()))

    def test_category_inactive_does_not_hide_article(self):
        space = _mk_space()
        cat = _mk_category(space, is_active=False)
        article, _ = _publish(
            _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES, space=space, category=cat)
        )
        self.assertIn(article, visible_articles(_mk_user()))

    def test_review_overdue_does_not_hide_article(self):
        article, _ = _publish(
            _mk_article(
                policy=AudiencePolicy.ALL_EMPLOYEES,
                review_due_at=timezone.now() - timedelta(days=1),
            )
        )
        self.assertIn(article, visible_articles(_mk_user()))


class SpaceDefaultPolicyTests(TestCase):
    """空间默认策略不作为阅读回退；修改默认不影响既有文章。"""

    def test_space_default_change_does_not_affect_existing_article(self):
        space = _mk_space(default_audience_policy=AudiencePolicy.RESTRICTED)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED, space=space))
        u = _mk_user()
        self.assertNotIn(article, visible_articles(u))
        space.default_audience_policy = AudiencePolicy.ALL_EMPLOYEES
        space.save(update_fields=["default_audience_policy"])
        self.assertNotIn(article, visible_articles(u))


class WriteValidationTests(TestCase):
    """受众写入一致性校验（模型 clean 层）。"""

    def test_restricted_allows_department_allow(self):
        article = _mk_article(policy=AudiencePolicy.RESTRICTED)
        dept = Department.objects.create(name="A")
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.ALLOW,
            department=dept,
            created_by=article.owner,
        )
        rule.full_clean()

    def test_restricted_rejects_all_employees_allow(self):
        article = _mk_article(policy=AudiencePolicy.RESTRICTED)
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            effect=AudienceEffect.ALLOW,
            created_by=article.owner,
        )
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_all_employees_allows_redundant_all_employees_allow(self):
        article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            effect=AudienceEffect.ALLOW,
            created_by=article.owner,
        )
        rule.full_clean()

    def test_all_employees_rejects_department_allow(self):
        article = _mk_article(policy=AudiencePolicy.ALL_EMPLOYEES)
        dept = Department.objects.create(name="A")
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.ALLOW,
            department=dept,
            created_by=article.owner,
        )
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_it_only_allows_redundant_it_only_allow(self):
        article = _mk_article(policy=AudiencePolicy.IT_ONLY)
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.IT_ONLY,
            effect=AudienceEffect.ALLOW,
            created_by=article.owner,
        )
        rule.full_clean()

    def test_it_only_rejects_department_allow(self):
        article = _mk_article(policy=AudiencePolicy.IT_ONLY)
        dept = Department.objects.create(name="A")
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.ALLOW,
            department=dept,
            created_by=article.owner,
        )
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_deny_always_allowed(self):
        for policy in (
            AudiencePolicy.RESTRICTED,
            AudiencePolicy.ALL_EMPLOYEES,
            AudiencePolicy.IT_ONLY,
        ):
            article = _mk_article(policy=policy)
            dept = Department.objects.create(name=f"拒绝-{policy}")
            rule = ArticleAudience(
                article=article,
                audience_type=AudienceType.DEPARTMENT,
                effect=AudienceEffect.DENY,
                department=dept,
                created_by=article.owner,
            )
            rule.full_clean()

    def test_article_clean_rejects_inconsistent_existing_allow_on_policy_change(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        dept = Department.objects.create(name="A")
        _add_audience(
            article, AudienceType.DEPARTMENT, effect=AudienceEffect.ALLOW, department=dept
        )
        article.audience_policy = AudiencePolicy.ALL_EMPLOYEES
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_bypassed_inconsistent_allow_not_expand_read(self):
        # 绕过校验直接落库 all_employees allow，读取侧仍按 restricted 计算，不扩大范围。
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            effect=AudienceEffect.ALLOW,
            created_by=article.owner,
        )
        self.assertNotIn(article, visible_articles(_mk_user()))

    def test_bypassed_deny_still_applied(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.DENY,
            department=dept,
            created_by=article.owner,
        )
        self.assertNotIn(article, visible_articles(u))


class DedupAndConsistencyTests(TestCase):
    """去重、base 保留、list == single 一致性。"""

    def test_multi_match_no_duplicate(self):
        dept = Department.objects.create(name="A")
        group = UserGroup.objects.create(name="G")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        UserGroupMembership.objects.create(user=u, user_group=group)
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        _add_audience(article, AudienceType.USER_GROUP, user_group=group)
        _add_audience(article, AudienceType.USER, user=u)
        self.assertEqual(list(visible_articles(u)).count(article), 1)

    def test_base_filter_preserved(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        article_visible, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article_visible, AudienceType.DEPARTMENT, department=dept)
        article_other, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        base = Article.objects.filter(pk=article_other.pk)
        result = visible_articles(u, base=base)
        self.assertNotIn(article_visible, result)
        self.assertIn(article_other, result)

    def test_list_and_single_consistent(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        visible, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(visible, AudienceType.DEPARTMENT, department=dept)
        hidden, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        for article in (visible, hidden):
            self.assertEqual(can_read_article(u, article), article in visible_articles(u))

    def test_can_read_article_none_and_unsaved(self):
        u = _mk_user()
        self.assertFalse(can_read_article(u, None))
        self.assertFalse(can_read_article(u, Article()))


class RefreshTests(TestCase):
    """关系 / 状态变化后再次调用返回最新结果（无跨请求缓存）。"""

    def test_department_relation_change_updates_result(self):
        dept = Department.objects.create(name="A")
        u = _mk_user()
        article, _ = _publish(_mk_article(policy=AudiencePolicy.RESTRICTED))
        _add_audience(article, AudienceType.DEPARTMENT, department=dept)
        self.assertNotIn(article, visible_articles(u))
        rel = UserDepartment.objects.create(user=u, department=dept)
        self.assertIn(article, visible_articles(u))
        rel.delete()
        self.assertNotIn(article, visible_articles(u))

    def test_article_status_change_updates_result(self):
        article, _ = _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))
        u = _mk_user()
        self.assertIn(article, visible_articles(u))
        article.article_status = ArticleStatus.OFFLINE
        article.save(update_fields=["article_status"])
        self.assertNotIn(article, visible_articles(u))


class QueryCountTests(TestCase):
    """代表性查询数证明：文章数量增长不导致逐篇查询（无 N+1）。"""

    def test_article_count_does_not_grow_queries(self):
        dept = Department.objects.create(name="A")
        group = UserGroup.objects.create(name="IT 运维组")
        u = _mk_user()
        UserDepartment.objects.create(user=u, department=dept)
        UserGroupMembership.objects.create(user=u, user_group=group)

        for _ in range(3):
            _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            with CaptureQueriesContext(connection) as small:
                list(visible_articles(u))

        for _ in range(20):
            _publish(_mk_article(policy=AudiencePolicy.ALL_EMPLOYEES))

        with self.settings(KNOWLEDGE_IT_USER_GROUP_ID=group.id):
            with CaptureQueriesContext(connection) as large:
                list(visible_articles(u))

        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
