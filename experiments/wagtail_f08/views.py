"""F08 最小员工普通文本详情页；业务读取全部委托 F06 正式快照入口。"""

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from experiments.wagtail_f06.readers import get_employee_article_detail


@csrf_exempt
def article_detail(request, article_id):
    """只处理 HTTP 边界；不复制受众、审核证据或正文格式判断。"""
    if request.method != "GET":
        response = HttpResponse("仅支持 GET 请求。", status=405)
        response["Allow"] = "GET"
        return response
    if not request.user.is_authenticated:
        return HttpResponse("需要登录。", status=401)
    detail = get_employee_article_detail(request.user, article_id)
    if detail is None:
        return HttpResponse("未找到。", status=404)
    return render(request, "wagtail_f08/article_detail.html", {"article": detail})
