"""知识库后台注册入口。"""

from django.contrib import admin

from .models import (
    Article,
    ArticleAudience,
    ArticleVersion,
    Category,
    KnowledgeSpace,
    ReviewRecord,
)


@admin.register(KnowledgeSpace)
class KnowledgeSpaceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "space_type",
        "owner",
        "default_audience_policy",
        "is_active",
    )
    list_filter = ("space_type", "is_active")
    search_fields = ("name", "code")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "space", "parent", "sort_order", "is_active")
    list_filter = ("space", "is_active")
    search_fields = ("name", "code")
    autocomplete_fields = ("space", "parent")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "kb_no",
        "title",
        "space",
        "category",
        "article_type",
        "article_status",
        "owner",
        "review_due_at",
    )
    list_filter = ("article_status", "article_type", "space")
    search_fields = ("kb_no", "title")
    autocomplete_fields = (
        "space",
        "category",
        "owner",
        "created_by",
        "updated_by",
        "current_published_version",
        "latest_working_version",
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        # 编号生成服务完成并接入安全创建流程前，禁止通过 Admin 新增文章，
        # 防止在未生成编号时写入空 kb_no；恢复新增前必须同步提供编号生成或拦截机制。
        return False


@admin.register(ArticleVersion)
class ArticleVersionAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "version_no",
        "status",
        "title",
        "submitted_at",
        "published_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("article__kb_no", "article__title", "title")
    autocomplete_fields = ("article", "created_by", "submitted_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ArticleAudience)
class ArticleAudienceAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "audience_type",
        "effect",
        "department",
        "user_group",
        "user",
    )
    list_filter = ("audience_type", "effect")
    search_fields = (
        "article__kb_no",
        "article__title",
        "department__name",
        "user_group__name",
        "user__username",
        "user__display_name",
    )
    autocomplete_fields = ("article", "department", "user_group", "user", "created_by")
    readonly_fields = ("created_at",)


@admin.register(ReviewRecord)
class ReviewRecordAdmin(admin.ModelAdmin):
    list_display = ("article_version", "review_type", "reviewer", "decision", "reviewed_at")
    list_filter = ("review_type", "decision")
    search_fields = (
        "article_version__article__kb_no",
        "article_version__article__title",
        "reviewer__username",
        "reviewer__display_name",
    )
    autocomplete_fields = ("article_version", "reviewer")
    readonly_fields = ("reviewed_at",)
