"""Task 12E-02：正式知识管理列表 Reader 与页面合同。"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.db.models.query import QuerySet
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountStatus, User
from apps.accounts.roles import (
    ROLE_EDITOR,
    ROLE_KNOWLEDGE_ADMIN,
    ROLE_REVIEWER,
    SYSTEM_ROLE_BY_CODE,
)
from apps.knowledge.models import (
    Article,
    ArticleStatus,
    ArticleType,
    ArticleVersion,
    AudiencePolicy,
    Category,
    KnowledgeSpace,
    VersionStatus,
)


class ManageArticleListBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("sync_system_roles", verbosity=0, stdout=StringIO())
        cls.editor_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_EDITOR].name)
        cls.admin_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_KNOWLEDGE_ADMIN].name)
        cls.reviewer_group = Group.objects.get(name=SYSTEM_ROLE_BY_CODE[ROLE_REVIEWER].name)

        cls.article_owner = cls.make_user("manage-article-owner", cls.editor_group)
        cls.space_owner = cls.make_user("manage-space-owner", cls.editor_group)
        cls.other_editor = cls.make_user("manage-other-editor", cls.editor_group)
        cls.admin = cls.make_user("manage-admin", cls.admin_group)
        cls.employee = cls.make_user("manage-employee")
        cls.reviewer = cls.make_user("manage-reviewer", cls.reviewer_group)

        cls.space = cls.make_space("manage-main", cls.space_owner)
        cls.category = cls.make_category(cls.space, "manage-main")
        cls.other_space = cls.make_space("manage-other", cls.other_editor)
        cls.other_category = cls.make_category(cls.other_space, "manage-other")
        cls.inactive_space = cls.make_space("manage-inactive", cls.space_owner, is_active=False)
        cls.inactive_category = cls.make_category(cls.inactive_space, "manage-inactive")

        cls.working_article = cls.make_article(
            "KB-280001",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="OLD-COMPAT-TITLE",
        )
        published = cls.make_version(
            cls.working_article,
            1,
            VersionStatus.PUBLISHED,
            "PUBLISHED-TITLE",
        )
        working = cls.make_version(
            cls.working_article,
            2,
            VersionStatus.DRAFT,
            "WORKING-TITLE",
        )
        Article.objects.filter(pk=cls.working_article.pk).update(
            current_published_version=published,
            latest_working_version=working,
        )

        cls.published_only_article = cls.make_article(
            "KB-280002",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="UNUSED-COMPAT-PUBLISHED",
        )
        published_only = cls.make_version(
            cls.published_only_article,
            1,
            VersionStatus.PUBLISHED,
            "PUBLISHED-ONLY-TITLE",
        )
        Article.objects.filter(pk=cls.published_only_article.pk).update(
            current_published_version=published_only
        )

        cls.no_version_article = cls.make_article(
            "KB-280003",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="NEVER-SHOW-COMPAT-TITLE",
        )
        cls.draft_only_article = cls.make_article(
            "KB-280004",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="UNUSED-DRAFT-COMPAT",
        )
        draft_only = cls.make_version(
            cls.draft_only_article,
            1,
            VersionStatus.DRAFT,
            "DRAFT-ONLY-TITLE",
        )
        Article.objects.filter(pk=cls.draft_only_article.pk).update(
            latest_working_version=draft_only
        )

        cls.denied_article = cls.make_article(
            "KB-280005",
            space=cls.other_space,
            category=cls.other_category,
            owner=cls.other_editor,
            title="DENIED-COMPAT",
        )
        denied_draft = cls.make_version(
            cls.denied_article,
            1,
            VersionStatus.DRAFT,
            "DENIED-SECRET-TITLE",
        )
        Article.objects.filter(pk=cls.denied_article.pk).update(latest_working_version=denied_draft)

        cls.inactive_space_article = cls.make_article(
            "KB-280006",
            space=cls.inactive_space,
            category=cls.inactive_category,
            owner=cls.article_owner,
            title="INACTIVE-SPACE-COMPAT",
        )

        cls.offline_article = cls.make_article(
            "KB-280007",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="OFFLINE-COMPAT",
            article_status=ArticleStatus.OFFLINE,
        )
        cls.archived_article = cls.make_article(
            "KB-280008",
            space=cls.space,
            category=cls.category,
            owner=cls.article_owner,
            title="ARCHIVED-COMPAT",
            article_status=ArticleStatus.ARCHIVED,
        )

    @classmethod
    def make_user(cls, username, group=None, **kwargs):
        user = User.objects.create_user(username=username, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    @classmethod
    def make_space(cls, code, owner, *, is_active=True):
        return KnowledgeSpace.objects.create(
            code=code,
            name=f"空间 {code}",
            space_type="employee",
            owner=owner,
            default_audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            is_active=is_active,
        )

    @classmethod
    def make_category(cls, space, code):
        return Category.objects.create(
            space=space,
            code=code,
            name=f"分类 {code}",
        )

    @classmethod
    def make_article(
        cls,
        kb_no,
        *,
        space,
        category,
        owner,
        title,
        article_status=ArticleStatus.ACTIVE,
    ):
        return Article.objects.create(
            kb_no=kb_no,
            title=title,
            space=space,
            category=category,
            article_type=ArticleType.GUIDE,
            audience_policy=AudiencePolicy.ALL_EMPLOYEES,
            owner=owner,
            article_status=article_status,
            created_by=owner,
            updated_by=owner,
            review_due_at=timezone.now() + timedelta(days=180),
        )

    @classmethod
    def make_version(cls, article, version_no, status, title):
        workflow_fields = {}
        if status not in (VersionStatus.DRAFT, VersionStatus.SAVED):
            workflow_fields.update(
                submitted_by=article.owner,
                submitted_at=timezone.now(),
            )
        if status == VersionStatus.PUBLISHED:
            workflow_fields["published_at"] = timezone.now()
        return ArticleVersion.objects.create(
            article=article,
            version_no=version_no,
            status=status,
            title=title,
            summary=f"{title} 摘要",
            body_plaintext=f"{title} 正文",
            change_summary=f"{title} 说明",
            created_by=article.owner,
            **workflow_fields,
        )

    def login(self, user):
        self.client.force_login(user)


class ManageArticleListReaderTests(ManageArticleListBase):
    def test_reader_returns_lazy_queryset_and_filters_editor_object_access(self):
        from apps.knowledge.manage_readers import get_manage_article_list

        result = get_manage_article_list(actor=self.article_owner)

        self.assertIsInstance(result, QuerySet)
        self.assertEqual(
            set(result.values_list("kb_no", flat=True)),
            {
                "KB-280001",
                "KB-280002",
                "KB-280003",
                "KB-280004",
                "KB-280007",
                "KB-280008",
            },
        )
        self.assertNotIn("KB-280005", result.values_list("kb_no", flat=True))
        self.assertNotIn("KB-280006", result.values_list("kb_no", flat=True))

    def test_space_owner_and_admin_visibility(self):
        from apps.knowledge.manage_readers import get_manage_article_list

        space_owner_rows = get_manage_article_list(actor=self.space_owner)
        admin_rows = get_manage_article_list(actor=self.admin)

        self.assertIn(self.working_article, space_owner_rows)
        self.assertNotIn(self.denied_article, space_owner_rows)
        self.assertIn(self.working_article, admin_rows)
        self.assertIn(self.denied_article, admin_rows)
        self.assertNotIn(self.inactive_space_article, admin_rows)

    def test_all_article_statuses_in_active_spaces_are_manageable(self):
        from apps.knowledge.manage_readers import get_manage_article_list

        rows = get_manage_article_list(actor=self.article_owner)

        self.assertIn(self.working_article, rows)
        self.assertIn(self.offline_article, rows)
        self.assertIn(self.archived_article, rows)

    def test_reader_requires_role_and_both_view_permissions(self):
        from apps.knowledge.manage_readers import (
            MANAGE_ARTICLE_LIST_PERMISSION_DENIED,
            ManageArticleListReadError,
            get_manage_article_list,
        )

        for actor in (self.employee, self.reviewer):
            with self.subTest(actor=actor.username):
                with self.assertRaises(ManageArticleListReadError) as caught:
                    get_manage_article_list(actor=actor)
                self.assertEqual(caught.exception.code, MANAGE_ARTICLE_LIST_PERMISSION_DENIED)

        for codename in ("view_article", "view_articleversion"):
            with self.subTest(codename=codename):
                permission = Permission.objects.get(
                    content_type__app_label="knowledge",
                    codename=codename,
                )
                self.editor_group.permissions.remove(permission)
                try:
                    with self.assertRaises(ManageArticleListReadError) as caught:
                        get_manage_article_list(actor=self.article_owner)
                    self.assertEqual(
                        caught.exception.code,
                        MANAGE_ARTICLE_LIST_PERMISSION_DENIED,
                    )
                finally:
                    self.editor_group.permissions.add(permission)

    def test_reader_is_read_only_without_employee_reader_or_row_locks(self):
        from apps.knowledge.manage_readers import get_manage_article_list

        before = list(Article.objects.order_by("pk").values())
        with (
            mock.patch.object(QuerySet, "select_for_update", side_effect=AssertionError),
            mock.patch(
                "apps.knowledge.readers.employee_visible_articles",
                side_effect=AssertionError,
            ),
        ):
            list(get_manage_article_list(actor=self.article_owner))

        self.assertEqual(list(Article.objects.order_by("pk").values()), before)


class ManageArticleListHttpAndPermissionTests(ManageArticleListBase):
    def test_route_and_get_contract(self):
        self.login(self.article_owner)

        response = self.client.get(reverse("knowledge_manage:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/manage/knowledge/")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_unauthenticated_inactive_and_business_inactive_are_401(self):
        url = "/manage/knowledge/"
        anonymous = self.client.get(url)

        inactive = self.make_user("manage-inactive-user", self.editor_group, is_active=False)
        inactive_client = Client()
        inactive_client.force_login(inactive)

        disabled = self.make_user(
            "manage-disabled-user",
            self.editor_group,
            account_status=AccountStatus.DISABLED,
        )
        disabled_client = Client()
        disabled_client.force_login(disabled)

        for response in (
            anonymous,
            inactive_client.get(url),
            disabled_client.get(url),
        ):
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_non_management_roles_staff_and_superuser_are_403(self):
        staff = self.make_user("manage-staff-only", is_staff=True)
        superuser = User.objects.create_superuser(
            username="manage-superuser-only",
            email="",
            password="not-used-in-test",
        )

        for actor in (self.employee, self.reviewer, staff, superuser):
            with self.subTest(actor=actor.username):
                client = Client()
                client.force_login(actor)
                response = client.get("/manage/knowledge/")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_missing_each_required_model_permission_is_403(self):
        for codename in ("view_article", "view_articleversion"):
            with self.subTest(codename=codename):
                permission = Permission.objects.get(
                    content_type__app_label="knowledge",
                    codename=codename,
                )
                self.editor_group.permissions.remove(permission)
                try:
                    client = Client()
                    client.force_login(self.article_owner)
                    response = client.get("/manage/knowledge/")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                finally:
                    self.editor_group.permissions.add(permission)

    def test_non_get_methods_are_405_with_allow_and_no_store(self):
        self.login(self.article_owner)
        for method in ("post", "put", "patch", "delete", "head"):
            with self.subTest(method=method):
                response = getattr(self.client, method)("/manage/knowledge/")
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")
                self.assertEqual(response["Cache-Control"], "private, no-store")


class ManageArticleListContentTests(ManageArticleListBase):
    def test_title_authority_and_version_summaries(self):
        self.login(self.article_owner)

        response = self.client.get("/manage/knowledge/")

        self.assertContains(response, "WORKING-TITLE")
        self.assertContains(response, "PUBLISHED-ONLY-TITLE")
        self.assertContains(response, "（无可用标题）")
        self.assertNotContains(response, "OLD-COMPAT-TITLE")
        self.assertNotContains(response, "UNUSED-COMPAT-PUBLISHED")
        self.assertNotContains(response, "NEVER-SHOW-COMPAT-TITLE")
        html = response.content.decode()
        self.assertRegex(html, r"v2\s+·\s+草稿")
        self.assertRegex(html, r"v1\s+·\s+已发布")
        self.assertContains(response, "未发布")

    def test_editor_page_does_not_leak_unauthorized_article_or_count(self):
        self.login(self.article_owner)

        response = self.client.get("/manage/knowledge/")

        self.assertNotContains(response, self.denied_article.kb_no)
        self.assertNotContains(response, "DENIED-SECRET-TITLE")
        self.assertEqual(response.context["pagination"]["count"], 6)

    def test_admin_can_see_articles_from_all_active_spaces(self):
        self.login(self.admin)

        response = self.client.get("/manage/knowledge/")

        self.assertContains(response, self.working_article.kb_no)
        self.assertContains(response, self.denied_article.kb_no)
        self.assertNotContains(response, self.inactive_space_article.kb_no)

    def test_draft_only_article_is_manageable_but_employee_reader_does_not_expose_it(self):
        from apps.knowledge.readers import employee_visible_articles

        self.login(self.article_owner)
        response = self.client.get("/manage/knowledge/")

        self.assertContains(response, self.draft_only_article.kb_no)
        self.assertNotIn(
            self.draft_only_article,
            employee_visible_articles(self.article_owner),
        )

    def test_template_autoescapes_management_title(self):
        ArticleVersion.objects.filter(
            article=self.working_article,
            status=VersionStatus.DRAFT,
        ).update(title='<script>alert("manage")</script>')
        self.login(self.article_owner)

        response = self.client.get("/manage/knowledge/")

        self.assertContains(response, "&lt;script&gt;alert", html=False)
        self.assertNotContains(response, '<script>alert("manage")</script>', html=False)


class ManageArticleListPaginationTests(ManageArticleListBase):
    def setUp(self):
        self.pagination_owner = self.make_user("manage-pagination-owner", self.editor_group)
        self.pagination_space = self.make_space("manage-pagination", self.pagination_owner)
        self.pagination_category = self.make_category(
            self.pagination_space,
            "manage-pagination",
        )
        for number in range(1, 22):
            self.make_article(
                f"KB-29{number:04d}",
                space=self.pagination_space,
                category=self.pagination_category,
                owner=self.pagination_owner,
                title=f"分页知识 {number:02d}",
            )
        self.login(self.pagination_owner)

    def test_page_size_and_safe_invalid_page_behavior(self):
        first = self.client.get("/manage/knowledge/")
        second = self.client.get("/manage/knowledge/?page=2")
        text_page = self.client.get("/manage/knowledge/?page=abc")
        overflow = self.client.get("/manage/knowledge/?page=999")

        self.assertEqual(first.context["pagination"]["count"], 21)
        self.assertEqual(len(first.context["articles"]), 20)
        self.assertEqual(len(second.context["articles"]), 1)
        self.assertEqual(text_page.context["pagination"]["number"], 1)
        self.assertEqual(overflow.context["pagination"]["number"], 2)


class ManageArticleListQueryTests(ManageArticleListBase):
    def test_query_count_is_constant_for_one_and_twenty_articles(self):
        small_owner = self.make_user("manage-query-small", self.editor_group)
        large_owner = self.make_user("manage-query-large", self.editor_group)
        small_space = self.make_space("manage-query-small", small_owner)
        large_space = self.make_space("manage-query-large", large_owner)
        small_category = self.make_category(small_space, "manage-query-small")
        large_category = self.make_category(large_space, "manage-query-large")

        self.make_article(
            "KB-281001",
            space=small_space,
            category=small_category,
            owner=small_owner,
            title="查询小样本",
        )
        for number in range(20):
            article = self.make_article(
                f"KB-282{number:03d}",
                space=large_space,
                category=large_category,
                owner=large_owner,
                title=f"查询大样本 {number}",
            )
            draft = self.make_version(
                article,
                1,
                VersionStatus.DRAFT,
                f"查询工作标题 {number}",
            )
            Article.objects.filter(pk=article.pk).update(latest_working_version=draft)

        small_count = self.request_query_count(small_owner)
        large_count = self.request_query_count(large_owner)

        self.assertEqual(small_count, large_count)
        self.assertLessEqual(large_count, 10)

    def request_query_count(self, actor):
        client = Client()
        client.force_login(actor)
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/manage/knowledge/")
        self.assertEqual(response.status_code, 200)
        return len(queries.captured_queries)


class ManageArticleListEmployeeRouteRegressionTests(ManageArticleListBase):
    def test_existing_employee_routes_remain_registered_and_work(self):
        self.login(self.employee)

        responses = (
            self.client.get(reverse("knowledge:home")),
            self.client.get(reverse("knowledge:category_detail", args=[self.category.pk])),
            self.client.get(reverse("knowledge:article_detail", args=[self.working_article.kb_no])),
            self.client.get(reverse("search:results"), {"q": "PUBLISHED"}),
        )

        for response in responses:
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 200)
