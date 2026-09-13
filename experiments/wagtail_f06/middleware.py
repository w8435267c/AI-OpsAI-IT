"""仅为 F06 详情路径设置缓存策略，包含中间件提前拒绝的响应。"""


class PrivateDetailResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith("/experiments/f06/articles/"):
            response["Cache-Control"] = "private, no-store"
        return response
