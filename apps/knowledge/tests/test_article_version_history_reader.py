"""Task 12D-04：管理侧 ArticleVersion 历史 Reader。"""

from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import ROLE_EDITOR, ROLE_KNOWLEDGE_ADMIN, SYSTEM_ROLE_BY_CODE
from apps.knowledge.models import (
    Article,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    VersionStatus,
)
from apps.knowledge.version_readers import (
    ArticleVersionHistoryReadError,
    get_article_version_history,
)


class ArticleVersionHistoryReaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0)
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)

        cls.article_owner = User.objects.create_user(username="history-article-owner")
        cls.article_owner.groups.add(editor_group)
        cls.space_owner = User.objects.create_user(username="history-space-owner")
        cls.space_owner.groups.add(editor_group)
        cls.other_editor = User.objects.create_user(username="history-other-editor")
        cls.other_editor.groups.add(editor_group)
        cls.admin = User.objects.create_user(username="history-admin")
        cls.admin.groups.add(admin_group)
        cls.employee = User.objects.create_user(username="history-employee")

        cls.space = KnowledgeSpace.objects.create(
            code="history-space",
            name="版本历史空间",
            space_type="employee",
            owner=cls.space_owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
        )
        cls.category = Category.objects.create(
            space=cls.space,
            code="history-category",
            name="版本历史分类",
        )
        cls.article = cls.make_article("KB-220001", cls.article_owner)
        cls.other_article = cls.make_article("KB-220002", cls.other_editor)

        statuses = (
            VersionStatus.SAVED,
            VersionStatus.IN_REVIEW,
            VersionStatus.REJECTED,
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
            VersionStatus.DRAFT,
        )
        cls.versions = []
        for version_no, status in enumerate(statuses, start=1):
            submitted_fields = {}
            if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
                submitted_fields = {
                    "submitted_by": cls.article_owner,
                    "submitted_at": timezone.now(),
                }
            if status == VersionStatus.PUBLISHED:
                submitted_fields["published_at"] = timezone.now()
            cls.versions.append(
                ArticleVersion.objects.create(
                    article=cls.article,
                    version_no=version_no,
                    status=status,
                    title=f"历史版本 {version_no}",
                    summary=f"历史摘要 {version_no}",
                    change_summary=f"历史说明 {version_no}",
                    created_by=cls.article_owner,
                    **submitted_fields,
                )
            )
        Article.objects.filter(pk=cls.article.pk).update(
            current_published_version=cls.versions[3],
            latest_working_version=cls.versions[5],
        )
        cls.other_version = ArticleVersion.objects.create(
            article=cls.other_article,
            version_no=99,
            status=VersionStatus.SAVED,
            title="其他文章版本",
            summary="其他文章摘要",
            change_summary="其他文章说明",
            created_by=cls.other_editor,
        )

    @classmethod
    def make_article(cls, kb_no, owner):
        return Article.objects.create(
            kb_no=kb_no,
            title=f"文章 {kb_no}",
            space=cls.space,
            category=cls.category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    def assert_reader_error(self, code, *, actor=None, article=None):
        with self.assertRaises(ArticleVersionHistoryReadError) as caught:
            get_article_version_history(
                actor=actor or self.article_owner,
                article=article or self.article,
            )
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_owner_space_owner_and_admin_can_read_history(self):
        for actor in (self.article_owner, self.space_owner, self.admin):
            with self.subTest(actor=actor.username):
                result = get_article_version_history(actor=actor, article=self.article)
                self.assertIsInstance(result, QuerySet)
                self.assertEqual(result.count(), 6)

    def test_reader_returns_only_requested_article_all_states_in_version_order(self):
        result = get_article_version_history(actor=self.article_owner, article=self.article)

        self.assertEqual(
            list(result.values_list("version_no", flat=True)),
            [6, 5, 4, 3, 2, 1],
        )
        self.assertEqual(
            set(result.values_list("status", flat=True)),
            set(VersionStatus.values),
        )
        self.assertNotIn(self.other_version.pk, result.values_list("pk", flat=True))

    def test_employee_staff_superuser_inactive_and_disabled_cannot_read(self):
        staff = User.objects.create_user(username="history-staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="history-superuser",
            email="",
            password="not-used-in-reader-test",
        )
        inactive = User.objects.create_user(username="history-inactive", is_active=False)
        inactive.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))
        disabled = User.objects.create_user(
            username="history-disabled",
            account_status=AccountStatus.DISABLED,
        )
        disabled.groups.add(Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name))

        for actor in (self.employee, staff, superuser, inactive, disabled):
            with self.subTest(actor=actor.username):
                self.assert_reader_error(
                    "ARTICLE_VERSION_HISTORY_PERMISSION_DENIED",
                    actor=actor,
                )

    def test_editor_without_object_access_and_missing_article_are_indistinguishable(self):
        denied = self.assert_reader_error(
            "ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE",
            actor=self.other_editor,
        )
        missing = Article(id=uuid4())
        missing_error = self.assert_reader_error(
            "ARTICLE_VERSION_HISTORY_NOT_FOUND_OR_INACCESSIBLE",
            article=missing,
        )

        self.assertEqual(denied.public_message, missing_error.public_message)

    def test_view_permissions_are_required_but_change_and_add_are_not(self):
        editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        for codename in ("view_article", "view_articleversion"):
            with self.subTest(required_permission=codename):
                permission = Permission.objects.get(
                    content_type__app_label="knowledge",
                    codename=codename,
                )
                editor_group.permissions.remove(permission)
                actor = User.objects.create_user(username=f"history-missing-{codename}")
                actor.groups.add(editor_group)
                self.assert_reader_error(
                    "ARTICLE_VERSION_HISTORY_PERMISSION_DENIED",
                    actor=actor,
                )
                editor_group.permissions.add(permission)

        for codename in ("change_article", "add_articleversion", "change_articleversion"):
            permission = Permission.objects.get(
                content_type__app_label="knowledge",
                codename=codename,
            )
            editor_group.permissions.remove(permission)
        actor = User.objects.create_user(username="history-view-only-owner")
        actor.groups.add(editor_group)
        Article.objects.filter(pk=self.article.pk).update(owner=actor)

        result = get_article_version_history(actor=actor, article=self.article)

        self.assertEqual(result.count(), 6)

    def test_reader_is_read_only_without_employee_reader_or_row_locks(self):
        article_before = Article.objects.values().get(pk=self.article.pk)
        versions_before = list(
            ArticleVersion.objects.filter(article=self.article).order_by("pk").values()
        )

        with (
            mock.patch.object(QuerySet, "select_for_update", side_effect=AssertionError),
            mock.patch(
                "apps.knowledge.readers.employee_visible_articles",
                side_effect=AssertionError,
            ),
        ):
            result = list(
                get_article_version_history(
                    actor=self.article_owner,
                    article=self.article,
                )
            )

        self.assertEqual(len(result), 6)
        self.assertEqual(Article.objects.values().get(pk=self.article.pk), article_before)
        self.assertEqual(
            list(ArticleVersion.objects.filter(article=self.article).order_by("pk").values()),
            versions_before,
        )
