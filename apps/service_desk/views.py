"""IT 服务入口视图。"""

from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect

from apps.knowledge.http import _private_no_store, has_active_employee_identity
from apps.knowledge.readers import get_employee_article_detail
from apps.service_desk.services import get_configured_service_request_url


def request_entry(request: HttpRequest, kb_no: str) -> HttpResponse:
    """仅允许已获文章阅读授权的员工跳转受控 IT 服务入口。"""
    if request.method != "GET":
        response = HttpResponse("仅支持 GET 请求。", status=405)
        response["Allow"] = "GET"
        return _private_no_store(response)
    if not has_active_employee_identity(request.user):
        return _private_no_store(HttpResponse("需要有效员工身份。", status=401))
    if get_employee_article_detail(request.user, kb_no) is None:
        return _private_no_store(HttpResponseNotFound("未找到可查看的知识。"))

    destination = get_configured_service_request_url()
    if destination is None:
        return _private_no_store(
            HttpResponse("IT 服务申请入口暂未配置，请联系 IT 支持。", status=503)
        )
    return _private_no_store(redirect(destination))
