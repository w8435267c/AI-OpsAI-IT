"""knowledge 数据模型的约束、关系、模型校验与删除策略测试。

数据库约束测试通过 objects.create() 绕过模型层校验，直接验证数据库行为，
并使用事务保存点捕获 IntegrityError，避免污染后续测试；
跨关系规则（如作者不能审核自己）只能在 clean()/full_clean() 层表达，
对应的测试会明确证明该规则不是数据库约束。
"""

from datetime import timedelta

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User, UserGroup

from ..admin import ArticleAdmin
from ..models import (
    Article,
    ArticleAudience,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudienceEffect,
    AudienceType,
    Category,
    KnowledgeSpace,
    ReviewDecision,
    ReviewRecord,
    ReviewType,
    VersionStatus,
)

_user_seq = 0
_space_seq = 0
_category_seq = 0


def create_user(username: str | None = None, **kwargs) -> User:
    global _user_seq
    if username is None:
        _user_seq += 1
        username = f"u{_user_seq}"
    return User.objects.create_user(username=username, **kwargs)


def make_space(owner: User | None = None, code: str | None = None, **kwargs) -> KnowledgeSpace:
    global _space_seq
    if owner is None:
        owner = create_user()
    if code is None:
        _space_seq += 1
        code = f"space{_space_seq}"
    kwargs.setdefault("name", "测试空间")
    return KnowledgeSpace.objects.create(code=code, owner=owner, **kwargs)


def make_category(space: KnowledgeSpace, code: str | None = None, **kwargs) -> Category:
    global _category_seq
    if code is None:
        _category_seq += 1
        code = f"cat{_category_seq}"
    kwargs.setdefault("name", "测试分类")
    return Category.objects.create(space=space, code=code, **kwargs)


def make_article(**kwargs) -> Article:
    space = kwargs.pop("space", None) or make_space()
    category = kwargs.pop("category", None) or make_category(space)
    owner = kwargs.pop("owner", None) or create_user()
    defaults = dict(
        kb_no="KB-000001",
        title="测试文章",
        space=space,
        category=category,
        article_type=ArticleType.GUIDE,
        owner=owner,
        created_by=owner,
        updated_by=owner,
        review_due_at=timezone.now() + timedelta(days=180),
    )
    defaults.update(kwargs)
    return Article.objects.create(**defaults)


def make_version(
    article: Article | None = None,
    version_no: int = 1,
    status: str = VersionStatus.DRAFT,
    created_by: User | None = None,
    **kwargs,
) -> ArticleVersion:
    if article is None:
        article = make_article()
    if created_by is None:
        created_by = article.created_by
    defaults = dict(
        article=article,
        version_no=version_no,
        status=status,
        title="版本标题",
        summary="版本摘要",
        change_summary="初始版本",
        created_by=created_by,
    )
    defaults.update(kwargs)
    return ArticleVersion.objects.create(**defaults)


def make_published_version(article: Article | None = None, **kwargs) -> ArticleVersion:
    submitter = create_user()
    now = timezone.now()
    return make_version(
        article=article,
        status=VersionStatus.PUBLISHED,
        submitted_by=submitter,
        submitted_at=now,
        published_at=now,
        **kwargs,
    )


class KnowledgeSpaceTests(TestCase):
    """知识空间的最小创建、唯一约束与删除策略。"""

    def test_minimal_space_can_be_created(self):
        space = make_space(name="员工知识空间")
        self.assertEqual(space.name, "员工知识空间")
        self.assertTrue(space.is_active)
        self.assertEqual(space.description, "")

    def test_space_code_unique_in_db(self):
        make_space(code="dup")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_space(code="dup")

    def test_deleting_owner_with_space_is_protected(self):
        owner = create_user()
        make_space(owner=owner)
        with self.assertRaises(ProtectedError):
            owner.delete()

    def test_str_is_name(self):
        space = make_space(name="IT 内部知识空间")
        self.assertEqual(str(space), "IT 内部知识空间")


class CategoryTests(TestCase):
    """分类的空间归属、同空间唯一编码、父子层级与删除策略。"""

    def test_minimal_category_can_be_created(self):
        space = make_space()
        category = make_category(space)
        self.assertEqual(category.space, space)
        self.assertIn(category, space.categories.all())
        self.assertTrue(category.is_active)
        self.assertIsNone(category.parent)

    def test_same_space_code_unique_in_db(self):
        space = make_space()
        make_category(space, code="dup")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_category(space, code="dup")

    def test_same_code_allowed_in_different_spaces(self):
        space_a = make_space(code="space-a")
        space_b = make_space(code="space-b")
        make_category(space_a, code="shared")
        other = make_category(space_b, code="shared")
        self.assertEqual(other.code, "shared")

    def test_parent_child_relationship(self):
        space = make_space()
        parent = make_category(space, code="p")
        child = make_category(space, code="c", parent=parent)
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())

    def test_parent_must_belong_to_same_space_full_clean(self):
        space_a = make_space(code="space-a")
        space_b = make_space(code="space-b")
        parent = make_category(space_b, code="p")
        child = make_category(space_a, code="c", parent=parent)
        with self.assertRaises(ValidationError):
            child.full_clean()

    def test_cross_space_parent_is_not_a_db_constraint(self):
        # 跨关系规则只在模型校验层表达：直接写库不会触发 IntegrityError
        space_a = make_space(code="space-a")
        space_b = make_space(code="space-b")
        parent = make_category(space_b, code="p")
        child = make_category(space_a, code="c", parent=parent)
        self.assertEqual(child.parent, parent)

    def test_category_cannot_be_its_own_parent(self):
        category = make_category(make_space())
        category.parent = category
        with self.assertRaises(ValidationError):
            category.full_clean()

    def test_deleting_parent_with_children_is_protected(self):
        space = make_space()
        parent = make_category(space, code="p")
        make_category(space, code="c", parent=parent)
        with self.assertRaises(ProtectedError):
            parent.delete()

    def test_deleting_space_with_categories_is_protected(self):
        space = make_space()
        make_category(space)
        with self.assertRaises(ProtectedError):
            space.delete()

    def test_str_is_name(self):
        category = make_category(make_space(), name="账号与权限")
        self.assertEqual(str(category), "账号与权限")


class ArticleTests(TestCase):
    """文章编号、状态、版本指针与删除策略。"""

    def test_minimal_article_can_be_created(self):
        article = make_article()
        self.assertEqual(article.article_status, ArticleStatus.ACTIVE)
        self.assertIsNone(article.current_published_version)
        self.assertIsNone(article.latest_working_version)

    def test_kb_no_format_validator_accepts_valid(self):
        article = make_article(kb_no="KB-000042")
        article.full_clean()

    def test_kb_no_format_validator_rejects_invalid(self):
        # 编号格式现由数据库约束兜底，非法值已无法落库；
        # 这里用未保存实例单独验证模型校验器仍能给出可读错误。
        space = make_space()
        category = make_category(space)
        owner = create_user()
        for bad in ("KB-00001", "KB-1", "kb-000001", "KB-0000001", "AB-000001"):
            with self.subTest(kb_no=bad):
                article = Article(
                    kb_no=bad,
                    title="测试文章",
                    space=space,
                    category=category,
                    article_type=ArticleType.GUIDE,
                    owner=owner,
                    created_by=owner,
                    updated_by=owner,
                    review_due_at=timezone.now() + timedelta(days=180),
                )
                with self.assertRaises(ValidationError):
                    article.full_clean()

    def test_kb_no_unique_in_db(self):
        make_article(kb_no="KB-000007")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_article(kb_no="KB-000007")

    def test_category_must_belong_to_article_space_full_clean(self):
        space = make_space(code="space-a")
        other_space = make_space(code="space-b")
        other_category = make_category(other_space, code="other")
        article = make_article(space=space, category=other_category)
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_published_pointer_must_belong_to_same_article(self):
        article = make_article()
        other = make_article(kb_no="KB-000002")
        version = make_published_version(other)
        article.current_published_version = version
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_published_pointer_requires_published_status(self):
        article = make_article()
        draft = make_version(article)
        article.current_published_version = draft
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_working_pointer_requires_working_status(self):
        article = make_article()
        published = make_published_version(article)
        article.latest_working_version = published
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_deleting_space_with_articles_is_protected(self):
        space = make_space(code="space-a")
        make_article(space=space)
        with self.assertRaises(ProtectedError):
            space.delete()

    def test_deleting_category_with_articles_is_protected(self):
        space = make_space(code="space-a")
        category = make_category(space)
        make_article(space=space, category=category)
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_str_contains_kb_no_and_title(self):
        article = make_article(kb_no="KB-000009", title="打印机离线")
        self.assertIn("KB-000009", str(article))
        self.assertIn("打印机离线", str(article))


class ArticleVersionTests(TestCase):
    """版本号唯一、工作/发布版本唯一、检查约束与删除策略。"""

    def test_minimal_version_can_be_created(self):
        version = make_version()
        self.assertEqual(version.status, VersionStatus.DRAFT)
        self.assertIn(version, version.article.versions.all())

    def test_version_no_unique_per_article_in_db(self):
        article = make_article()
        make_version(article, version_no=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_version(article, version_no=1)

    def test_same_version_no_allowed_for_different_articles(self):
        article_a = make_article()
        article_b = make_article(kb_no="KB-000002")
        make_version(article_a, version_no=1)
        other = make_version(article_b, version_no=1)
        self.assertEqual(other.version_no, 1)

    def test_only_one_working_version_per_article(self):
        article = make_article()
        make_version(article, status=VersionStatus.DRAFT)
        submitter = create_user()
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_version(
                article,
                version_no=2,
                status=VersionStatus.IN_REVIEW,
                submitted_by=submitter,
                submitted_at=now,
            )

    def test_working_version_and_published_version_can_coexist(self):
        article = make_article()
        make_published_version(article)
        working = make_version(article, version_no=2, status=VersionStatus.DRAFT)
        self.assertEqual(working.status, VersionStatus.DRAFT)

    def test_only_one_published_version_per_article(self):
        article = make_article()
        make_published_version(article)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_published_version(article, version_no=2)

    def test_version_no_must_be_positive_db_check(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_version(version_no=0)

    def test_non_draft_requires_submitted_info_db_check(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_version(status=VersionStatus.IN_REVIEW)

    def test_published_requires_published_at_db_check(self):
        submitter = create_user()
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_version(
                status=VersionStatus.PUBLISHED,
                submitted_by=submitter,
                submitted_at=now,
            )

    def test_published_requires_published_at_full_clean(self):
        submitter = create_user()
        now = timezone.now()
        version = make_version(
            status=VersionStatus.PUBLISHED,
            submitted_by=submitter,
            submitted_at=now,
            published_at=now,
        )
        # 构造一个未落库、缺发布时间但仍处于已发布状态的实例做模型校验
        version.published_at = None
        with self.assertRaises(ValidationError):
            version.full_clean()

    def test_non_draft_requires_submitted_info_full_clean(self):
        article = make_article()
        version = ArticleVersion(
            article=article,
            version_no=1,
            status=VersionStatus.REJECTED,
            title="版本标题",
            summary="版本摘要",
            change_summary="初始版本",
            created_by=article.created_by,
        )
        with self.assertRaises(ValidationError):
            version.full_clean()

    def test_deleting_article_with_versions_is_protected(self):
        version = make_version()
        with self.assertRaises(ProtectedError):
            version.article.delete()

    def test_deleting_creator_with_versions_is_protected(self):
        version = make_version()
        with self.assertRaises(ProtectedError):
            version.created_by.delete()

    def test_str_format(self):
        version = make_version(version_no=3)
        self.assertEqual(str(version), f"{version.article.kb_no} v3")


class ArticleAudienceTests(TestCase):
    """受众目标互斥、类型匹配、重复规则与删除策略。"""

    def test_minimal_department_rule_can_be_created(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        rule = ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.ALLOW,
            department=department,
            created_by=article.created_by,
        )
        self.assertIn(rule, article.audience_rules.all())

    def test_target_fields_mutually_exclusive_db_check(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        target_user = create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.DEPARTMENT,
                department=department,
                user=target_user,
                created_by=article.created_by,
            )

    def test_all_employees_cannot_carry_targets_db_check(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.ALL_EMPLOYEES,
                department=department,
                created_by=article.created_by,
            )

    def test_specific_type_requires_matching_target_db_check(self):
        article = make_article()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.USER,
                created_by=article.created_by,
            )

    def test_all_employees_must_be_allow_db_check(self):
        article = make_article()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.ALL_EMPLOYEES,
                effect=AudienceEffect.DENY,
                created_by=article.created_by,
            )

    def test_duplicate_rule_raises_integrity_error(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        defaults = dict(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            department=department,
            created_by=article.created_by,
        )
        ArticleAudience.objects.create(**defaults)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(**defaults)

    def test_allow_and_deny_for_same_target_can_coexist(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.ALLOW,
            department=department,
            created_by=article.created_by,
        )
        deny = ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            effect=AudienceEffect.DENY,
            department=department,
            created_by=article.created_by,
        )
        self.assertEqual(deny.effect, AudienceEffect.DENY)

    def test_all_employees_unique_per_article_in_db(self):
        article = make_article()
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            created_by=article.created_by,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.ALL_EMPLOYEES,
                created_by=article.created_by,
            )

    def test_it_only_unique_per_article_in_db(self):
        article = make_article()
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.IT_ONLY,
            created_by=article.created_by,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticleAudience.objects.create(
                article=article,
                audience_type=AudienceType.IT_ONLY,
                created_by=article.created_by,
            )

    def test_clean_rejects_target_for_all_employees(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        rule = ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            created_by=article.created_by,
        )
        # 数据库形状约束已在落库时拒绝该组合；这里验证模型层给出可读错误信息
        rule.department = department
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_clean_rejects_missing_target(self):
        article = make_article()
        rule = ArticleAudience(
            article=article,
            audience_type=AudienceType.USER_GROUP,
            created_by=article.created_by,
        )
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_deleting_article_with_rules_is_protected(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            department=department,
            created_by=article.created_by,
        )
        with self.assertRaises(ProtectedError):
            article.delete()

    def test_deleting_department_with_rules_is_protected(self):
        article = make_article()
        department = Department.objects.create(name="测试部门")
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.DEPARTMENT,
            department=department,
            created_by=article.created_by,
        )
        with self.assertRaises(ProtectedError):
            department.delete()

    def test_deleting_user_group_with_rules_is_protected(self):
        article = make_article()
        group = UserGroup.objects.create(name="新员工")
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.USER_GROUP,
            user_group=group,
            created_by=article.created_by,
        )
        with self.assertRaises(ProtectedError):
            group.delete()

    def test_deleting_target_user_with_rules_is_protected(self):
        article = make_article()
        target_user = create_user()
        ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.USER,
            user=target_user,
            created_by=article.created_by,
        )
        with self.assertRaises(ProtectedError):
            target_user.delete()

    def test_str_contains_kb_no_type_and_effect(self):
        article = make_article()
        rule = ArticleAudience.objects.create(
            article=article,
            audience_type=AudienceType.ALL_EMPLOYEES,
            created_by=article.created_by,
        )
        self.assertIn(article.kb_no, str(rule))
        self.assertIn("全员", str(rule))
        self.assertIn("允许", str(rule))


class ReviewRecordTests(TestCase):
    """作者不得自审、负面结论必须填写意见与删除策略。"""

    def test_minimal_review_record_can_be_created(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord.objects.create(
            article_version=version,
            review_type=ReviewType.CONTENT_REVIEW,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
        )
        self.assertEqual(record.decision, ReviewDecision.APPROVED)

    def test_author_cannot_review_own_version_full_clean(self):
        version = make_version()
        record = ReviewRecord(
            article_version=version,
            reviewer=version.created_by,
            decision=ReviewDecision.APPROVED,
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_author_self_review_is_not_a_db_constraint(self):
        # 跨表规则只能由模型校验层表达：直接写库不会被数据库拒绝
        version = make_version()
        record = ReviewRecord.objects.create(
            article_version=version,
            reviewer=version.created_by,
            decision=ReviewDecision.APPROVED,
        )
        self.assertIsNotNone(record.id)

    def test_non_author_review_full_clean_passes(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
        )
        record.full_clean()

    def test_reject_requires_comment_db_check(self):
        version = make_version()
        reviewer = create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReviewRecord.objects.create(
                article_version=version,
                reviewer=reviewer,
                decision=ReviewDecision.REJECTED,
                comment="",
            )

    def test_reject_with_comment_allowed(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.REJECTED,
            comment="步骤存在安全风险",
        )
        self.assertEqual(record.comment, "步骤存在安全风险")

    def test_approved_without_comment_allowed(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
            comment="",
        )
        self.assertEqual(record.decision, ReviewDecision.APPROVED)

    def test_reject_without_comment_full_clean(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.REVISION_REQUIRED,
            comment="",
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_deleting_version_with_review_is_protected(self):
        version = make_version()
        reviewer = create_user()
        ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
        )
        with self.assertRaises(ProtectedError):
            version.delete()

    def test_deleting_reviewer_with_review_is_protected(self):
        version = make_version()
        reviewer = create_user()
        ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
        )
        with self.assertRaises(ProtectedError):
            reviewer.delete()

    def test_str_contains_kb_no_and_decision(self):
        version = make_version()
        reviewer = create_user()
        record = ReviewRecord.objects.create(
            article_version=version,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVED,
        )
        self.assertIn(version.article.kb_no, str(record))
        self.assertIn("审核通过", str(record))


class ArticleKbNoDbFormatTests(TestCase):
    """编号格式数据库检查约束：绕过模型校验直接写库验证。"""

    def _create_with_kb_no(self, kb_no: str) -> Article:
        space = make_space()
        category = make_category(space)
        owner = create_user()
        return Article.objects.create(
            kb_no=kb_no,
            title="编号格式测试",
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def test_empty_kb_no_rejected_by_db(self):
        # objects.create() 绕过模型校验，证明空编号由数据库约束拒绝
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create_with_kb_no("")

    def test_illegal_kb_no_formats_rejected_by_db(self):
        bad_values = (
            "KA-000001",  # 错误前缀
            "KB-00001",  # 数字不足 6 位
            "kb-000001",  # 小写前缀
            "KB-00001a",  # 含字母
            "KB-00001 ",  # 含空格
            "KB-٠٠٠٠٠١",  # 非 ASCII 数字（阿拉伯-印度数字）
        )
        for bad in bad_values:
            with self.subTest(kb_no=bad):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self._create_with_kb_no(bad)

    def test_valid_kb_no_accepted_by_db(self):
        article = self._create_with_kb_no("KB-000001")
        self.assertEqual(article.kb_no, "KB-000001")


class ArticleAdminTests(TestCase):
    """编号生成服务落地前 Admin 新增入口关闭，查看与编辑不受影响。"""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="kb-admin", password="test-admin-password"
        )
        self.article = make_article()

    def _admin_instance(self) -> ArticleAdmin:
        return ArticleAdmin(Article, admin.site)

    def test_has_add_permission_returns_false(self):
        request = RequestFactory().get("/admin/knowledge/article/add/")
        request.user = self.admin_user
        self.assertFalse(self._admin_instance().has_add_permission(request))

    def test_add_url_rejected_even_with_admin_privileges(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin:knowledge_article_add")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        # 直接访问新增 URL 也无法创建任何文章记录
        self.assertEqual(Article.objects.count(), 1)

    def test_change_view_remains_accessible(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin:knowledge_article_change", args=[self.article.id])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_existing_article_can_be_edited_via_admin(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin:knowledge_article_change", args=[self.article.id])
        data = {
            "title": "Admin 更新后的标题",
            "space": str(self.article.space_id),
            "category": str(self.article.category_id),
            "article_type": ArticleType.GUIDE,
            "audience_policy": self.article.audience_policy,
            "owner": str(self.article.owner_id),
            "article_status": self.article.article_status,
            "effective_at_0": "",
            "effective_at_1": "",
            "review_due_at_0": "2030-01-01",
            "review_due_at_1": "12:00:00",
            "current_published_version": "",
            "latest_working_version": "",
            "created_by": str(self.article.created_by_id),
            "updated_by": str(self.article.created_by_id),
            "_save": "保存",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "Admin 更新后的标题")
