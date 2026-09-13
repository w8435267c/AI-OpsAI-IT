"""仅负责实验员工详情的 HTTP 输入输出。"""

from django.http import JsonResponse

from .readers import get_employee_article_detail


def article_detail(request, article_id):
    if request.method != "GET":
        response = JsonResponse({"error": "method_not_allowed"}, status=405)
        response["Allow"] = "GET"
        return response
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication_required"}, status=401)
    detail = get_employee_article_detail(request.user, article_id)
    if detail is None:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {
            "article_id": str(detail.article_id),
            "content_id": detail.content_id,
            "revision_id": detail.revision_id,
            "title": detail.title,
            "summary": detail.summary,
            "body": detail.body,
        }
    )
