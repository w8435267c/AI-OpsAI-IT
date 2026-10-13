"""Task 13 审核工作流的正式纯只读数据入口。"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q

from apps.accounts.models import AccountStatus, User
from apps.knowledge.models import (
    Article,
    ArticleVersion,
    ReviewDecision,
    ReviewRecord,
    ReviewType,
    VersionStatus,
)
from apps.knowledge.services import (
    _has_article_version_object_access,
    _resolve_writer_actor,
)
from apps.workflow.services import _resolve_reviewer_actor

INVALID_INPUT = "INVALID_INPUT"
IDENTITY_DENIED = "IDENTITY_DENIED"
REVIEW_FORBIDDEN = "REVIEW_FORBIDDEN"
ARTICLE_NOT_FOUND_OR_INACCESSIBLE = "ARTICLE_NOT_FOUND_OR_INACCESSIBLE"
VERSION_NOT_FOUND_OR_INACCESSIBLE = "VERSION_NOT_FOUND_OR_INACCESSIBLE"

_KB_NO_PATTERN = re.compile(r"^KB-[0-9]{6}$")
_REVIEW_PERMISSION = "knowledge.review_articleversion"
_MANAGE_READ_PERMISSIONS = (
    "knowledge.view_article",
    "knowledge.view_articleversion",
)
_HISTORICAL_REVIEW_STATUSES = (
    VersionStatus.REJECTED,
    VersionStatus.PUBLISHED,
    VersionStatus.SUPERSEDED,
)


class WorkflowReaderError(Exception):
    """工作流只读查询失败的稳定安全异常。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PendingReviewItem:
    article_id: UUID
    kb_no: str
    version_id: UUID
    version_no: int
    title: str
    change_summary: str
    space_id: UUID
    space_code: str
    space_name: str
    submitted_by_id: UUID
    submitted_at: datetime
    article_type: str
    current_published_version_id: UUID | None
    current_published_version_no: int | None
    is_republish: bool


@dataclass(frozen=True, slots=True)
class ReviewTargetSnapshot:
    version_id: UUID
    version_no: int
    status: str
    title: str
    summary: str
    applicable_scope: object
    body: object
    body_plaintext: str
    change_summary: str
    created_by_id: UUID
    submitted_by_id: UUID | None
    submitted_at: datetime | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReviewArticleSnapshot:
    article_id: UUID
    kb_no: str
    article_type: str
    audience_policy: str
    article_status: str
    effective_at: datetime | None
    review_due_at: datetime
    owner_id: UUID
    space_id: UUID
    space_code: str
    space_name: str
    category_id: UUID
    category_code: str
    category_name: str
    current_published_version_id: UUID | None


@dataclass(frozen=True, slots=True)
class PublishedVersionSummary:
    version_id: UUID
    version_no: int
    title: str
    summary: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class VersionHistorySummary:
    version_id: UUID
    version_no: int
    status: str
    title: str
    change_summary: str
    submitted_by_id: UUID | None
    submitted_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    is_current_published: bool
    is_current_working: bool


@dataclass(frozen=True, slots=True)
class ReviewRecordSummary:
    review_record_id: UUID
    review_type: str
    decision: str
    reviewer_id: UUID
    comment: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewDetail:
    target: ReviewTargetSnapshot
    article: ReviewArticleSnapshot
    current_published: PublishedVersionSummary | None
    history: tuple[VersionHistorySummary, ...]
    review_records: tuple[ReviewRecordSummary, ...]


@dataclass(frozen=True, slots=True)
class ReviewedByMeItem:
    review_record_id: UUID
    decision: str
    reviewed_at: datetime
    article_id: UUID
    kb_no: str
    version_id: UUID
    version_no: int
    title: str
    space_id: UUID
    space_name: str
    submitted_by_id: UUID | None
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class SubmittedArticleStatus:
    article_id: UUID
    kb_no: str
    article_title_projection: str
    version_id: UUID
    version_no: int
    version_title: str
    status: str
    submitted_by_id: UUID
    submitted_at: datetime
    change_summary: str
    current_published_version_id: UUID | None
    current_published_version_no: int | None
    current_published_title: str | None


@dataclass(frozen=True, slots=True)
class RejectionContext:
    review_record_id: UUID
    rejected_version_id: UUID
    rejected_version_no: int
    rejected_version_title: str
    reviewer_id: UUID
    reviewed_at: datetime
    comment: str
    current_working_version_id: UUID | None
    current_working_version_no: int | None


def _resolve_reader_reviewer(actor) -> User:
    return _resolve_reviewer_actor(
        actor,
        required_permissions=(_REVIEW_PERMISSION,),
        error_type=WorkflowReaderError,
        forbidden_code=REVIEW_FORBIDDEN,
        identity_message="当前账号不能读取审核数据。",
        forbidden_message="没有读取审核数据的权限。",
    )


def _resolve_manage_reader(actor) -> tuple[User, bool]:
    if (
        not isinstance(actor, User)
        or actor.pk is None
        or actor._state.adding
        or not actor.is_authenticated
    ):
        raise WorkflowReaderError(IDENTITY_DENIED, "当前账号不能读取管理数据。")
    try:
        persisted_actor = User.objects.get(pk=actor.pk)
    except User.DoesNotExist as exc:
        raise WorkflowReaderError(
            IDENTITY_DENIED,
            "当前账号不能读取管理数据。",
        ) from exc
    if not persisted_actor.is_active or persisted_actor.account_status != AccountStatus.ACTIVE:
        raise WorkflowReaderError(IDENTITY_DENIED, "当前账号不能读取管理数据。")
    current_actor, is_admin, _is_editor = _resolve_writer_actor(
        actor=persisted_actor,
        user_query=User.objects,
        required_permissions=_MANAGE_READ_PERMISSIONS,
        error_type=WorkflowReaderError,
        error_code=ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
        public_message="文章不存在或不可访问。",
    )
    return current_actor, is_admin


def _normalize_version_id(version_id) -> UUID:
    try:
        normalized = ArticleVersion._meta.pk.to_python(version_id)
    except (TypeError, ValueError, ValidationError) as exc:
        raise WorkflowReaderError(INVALID_INPUT, "文章版本标识格式无效。") from exc
    if normalized is None:
        raise WorkflowReaderError(INVALID_INPUT, "文章版本标识格式无效。")
    return normalized


def _validate_kb_no(kb_no) -> str:
    if not isinstance(kb_no, str) or not _KB_NO_PATTERN.fullmatch(kb_no):
        raise WorkflowReaderError(INVALID_INPUT, "知识编号格式无效。")
    return kb_no


def _raise_version_not_found() -> None:
    raise WorkflowReaderError(
        VERSION_NOT_FOUND_OR_INACCESSIBLE,
        "文章版本不存在或不可访问。",
    )


def _raise_article_not_found() -> None:
    raise WorkflowReaderError(
        ARTICLE_NOT_FOUND_OR_INACCESSIBLE,
        "文章不存在或不可访问。",
    )


def list_pending_reviews(actor) -> tuple[PendingReviewItem, ...]:
    """返回当前 Reviewer 真正有资格处理的共享待审池摘要。"""
    current_actor = _resolve_reader_reviewer(actor)
    versions = (
        ArticleVersion.objects.filter(
            status=VersionStatus.IN_REVIEW,
            article__space__is_active=True,
            article__space__reviewer_scopes__reviewer=current_actor,
            article__space__reviewer_scopes__is_active=True,
        )
        .exclude(Q(created_by=current_actor) | Q(submitted_by=current_actor))
        .select_related("article__space", "article__current_published_version")
        .order_by("submitted_at", "article__kb_no", "version_no", "pk")
    )
    return tuple(
        PendingReviewItem(
            article_id=version.article_id,
            kb_no=version.article.kb_no,
            version_id=version.pk,
            version_no=version.version_no,
            title=version.title,
            change_summary=version.change_summary,
            space_id=version.article.space_id,
            space_code=version.article.space.code,
            space_name=version.article.space.name,
            submitted_by_id=version.submitted_by_id,
            submitted_at=version.submitted_at,
            article_type=version.article.article_type,
            current_published_version_id=version.article.current_published_version_id,
            current_published_version_no=(
                version.article.current_published_version.version_no
                if version.article.current_published_version_id is not None
                else None
            ),
            is_republish=version.article.current_published_version_id is not None,
        )
        for version in versions
    )


def _review_detail_target(*, actor: User, version_id: UUID) -> ArticleVersion:
    own_content_review = ReviewRecord.objects.filter(
        article_version_id=OuterRef("pk"),
        reviewer=actor,
        review_type=ReviewType.CONTENT_REVIEW,
    )
    target = (
        ArticleVersion.objects.annotate(_reviewed_by_actor=Exists(own_content_review))
        .filter(
            pk=version_id,
            article__space__is_active=True,
            article__space__reviewer_scopes__reviewer=actor,
            article__space__reviewer_scopes__is_active=True,
        )
        .filter(
            (Q(status=VersionStatus.IN_REVIEW) & ~Q(created_by=actor) & ~Q(submitted_by=actor))
            | (Q(status__in=_HISTORICAL_REVIEW_STATUSES) & Q(_reviewed_by_actor=True))
        )
        .select_related(
            "article__space",
            "article__category",
            "article__current_published_version",
        )
        .first()
    )
    if target is None:
        _raise_version_not_found()
    return target


def _published_summary(article: Article) -> PublishedVersionSummary | None:
    version = article.current_published_version
    if version is None:
        return None
    return PublishedVersionSummary(
        version_id=version.pk,
        version_no=version.version_no,
        title=version.title,
        summary=version.summary,
        published_at=version.published_at,
    )


def get_review_detail(*, actor, version_id) -> ReviewDetail:
    """返回待审目标或本人已处理历史的字段白名单快照。"""
    current_actor = _resolve_reader_reviewer(actor)
    target = _review_detail_target(
        actor=current_actor,
        version_id=_normalize_version_id(version_id),
    )
    article = target.article
    history = tuple(
        VersionHistorySummary(
            version_id=version.pk,
            version_no=version.version_no,
            status=version.status,
            title=version.title,
            change_summary=version.change_summary,
            submitted_by_id=version.submitted_by_id,
            submitted_at=version.submitted_at,
            published_at=version.published_at,
            created_at=version.created_at,
            is_current_published=article.current_published_version_id == version.pk,
            is_current_working=article.latest_working_version_id == version.pk,
        )
        for version in ArticleVersion.objects.filter(article=article).order_by("-version_no", "-pk")
    )
    review_records = tuple(
        ReviewRecordSummary(
            review_record_id=record.pk,
            review_type=record.review_type,
            decision=record.decision,
            reviewer_id=record.reviewer_id,
            comment=record.comment,
            reviewed_at=record.reviewed_at,
        )
        for record in ReviewRecord.objects.filter(article_version=target).order_by(
            "-reviewed_at", "-pk"
        )
    )
    return ReviewDetail(
        target=ReviewTargetSnapshot(
            version_id=target.pk,
            version_no=target.version_no,
            status=target.status,
            title=target.title,
            summary=target.summary,
            applicable_scope=deepcopy(target.applicable_scope),
            body=deepcopy(target.body),
            body_plaintext=target.body_plaintext,
            change_summary=target.change_summary,
            created_by_id=target.created_by_id,
            submitted_by_id=target.submitted_by_id,
            submitted_at=target.submitted_at,
            published_at=target.published_at,
        ),
        article=ReviewArticleSnapshot(
            article_id=article.pk,
            kb_no=article.kb_no,
            article_type=article.article_type,
            audience_policy=article.audience_policy,
            article_status=article.article_status,
            effective_at=article.effective_at,
            review_due_at=article.review_due_at,
            owner_id=article.owner_id,
            space_id=article.space_id,
            space_code=article.space.code,
            space_name=article.space.name,
            category_id=article.category_id,
            category_code=article.category.code,
            category_name=article.category.name,
            current_published_version_id=article.current_published_version_id,
        ),
        current_published=_published_summary(article),
        history=history,
        review_records=review_records,
    )


def list_reviewed_by_me(actor) -> tuple[ReviewedByMeItem, ...]:
    """返回当前授权范围内由本人形成的发布审核结论摘要。"""
    current_actor = _resolve_reader_reviewer(actor)
    records = (
        ReviewRecord.objects.filter(
            reviewer=current_actor,
            review_type=ReviewType.CONTENT_REVIEW,
            article_version__article__space__is_active=True,
            article_version__article__space__reviewer_scopes__reviewer=current_actor,
            article_version__article__space__reviewer_scopes__is_active=True,
        )
        .select_related("article_version__article__space")
        .order_by("-reviewed_at", "-pk")
    )
    return tuple(
        ReviewedByMeItem(
            review_record_id=record.pk,
            decision=record.decision,
            reviewed_at=record.reviewed_at,
            article_id=record.article_version.article_id,
            kb_no=record.article_version.article.kb_no,
            version_id=record.article_version_id,
            version_no=record.article_version.version_no,
            title=record.article_version.title,
            space_id=record.article_version.article.space_id,
            space_name=record.article_version.article.space.name,
            submitted_by_id=record.article_version.submitted_by_id,
            submitted_at=record.article_version.submitted_at,
        )
        for record in records
    )


def _managed_article(*, actor, kb_no: str) -> tuple[User, Article, bool]:
    current_actor, is_admin = _resolve_manage_reader(actor)
    try:
        article = Article.objects.select_related(
            "space",
            "current_published_version",
            "latest_working_version",
        ).get(kb_no=kb_no, space__is_active=True)
    except Article.DoesNotExist as exc:
        try:
            _raise_article_not_found()
        except WorkflowReaderError as error:
            raise error from exc
    if not _has_article_version_object_access(
        actor=current_actor,
        article=article,
        is_admin=is_admin,
    ):
        _raise_article_not_found()
    return current_actor, article, is_admin


def get_submitted_article_status(*, actor, kb_no) -> SubmittedArticleStatus | None:
    """返回管理对象当前唯一 IN_REVIEW 版本及正式版本摘要。"""
    _validate_kb_no(kb_no)
    _current_actor, article, _is_admin = _managed_article(actor=actor, kb_no=kb_no)
    target = (
        ArticleVersion.objects.filter(article=article, status=VersionStatus.IN_REVIEW)
        .order_by("version_no", "pk")
        .first()
    )
    if target is None:
        return None
    published = article.current_published_version
    return SubmittedArticleStatus(
        article_id=article.pk,
        kb_no=article.kb_no,
        article_title_projection=article.title,
        version_id=target.pk,
        version_no=target.version_no,
        version_title=target.title,
        status=target.status,
        submitted_by_id=target.submitted_by_id,
        submitted_at=target.submitted_at,
        change_summary=target.change_summary,
        current_published_version_id=article.current_published_version_id,
        current_published_version_no=published.version_no if published else None,
        current_published_title=published.title if published else None,
    )


def get_rejection_context(*, actor, kb_no) -> RejectionContext | None:
    """返回管理对象最近一次正式驳回结论和当前工作草稿引用。"""
    _validate_kb_no(kb_no)
    _current_actor, article, _is_admin = _managed_article(actor=actor, kb_no=kb_no)
    record = (
        ReviewRecord.objects.filter(
            article_version__article=article,
            review_type=ReviewType.CONTENT_REVIEW,
            decision=ReviewDecision.REJECTED,
        )
        .select_related("article_version")
        .order_by("-reviewed_at", "-article_version__version_no", "-pk")
        .first()
    )
    if record is None:
        return None
    working = article.latest_working_version
    if working is not None and working.status != VersionStatus.DRAFT:
        working = None
    return RejectionContext(
        review_record_id=record.pk,
        rejected_version_id=record.article_version_id,
        rejected_version_no=record.article_version.version_no,
        rejected_version_title=record.article_version.title,
        reviewer_id=record.reviewer_id,
        reviewed_at=record.reviewed_at,
        comment=record.comment,
        current_working_version_id=working.pk if working else None,
        current_working_version_no=working.version_no if working else None,
    )
