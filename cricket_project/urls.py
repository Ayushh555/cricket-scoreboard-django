from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache
from django.views.static import serve

FRONTEND = settings.BASE_DIR / "frontend"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("scoring.urls")),                                   # /api/...
    path("", never_cache(serve), {"document_root": FRONTEND, "path": "index.html"}),  # home page
    re_path(r"^(?P<path>(?:css|js)/.+|[\w-]+\.html)$", never_cache(serve), {"document_root": FRONTEND}),  # never cached: edits show up on refresh
]
