"""正式员工搜索页面路由。"""

from django.urls import path

from apps.search.views import employee_search_results

app_name = "search"

urlpatterns = [
    path("search/", employee_search_results, name="results"),
]
