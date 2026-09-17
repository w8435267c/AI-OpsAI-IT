"""只为 F08 员工详情页设置私有且禁止存储的缓存策略。"""


class PrivateArticlePageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith("/experiments/f08/articles/"):
            response["Cache-Control"] = "private, no-store"
        return response
