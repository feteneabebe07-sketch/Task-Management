from django.urls import path
from django.http import JsonResponse


def api_root(request):
    """Minimal API root for frontend JS to reference."""
    return JsonResponse({"detail": "API root"})


urlpatterns = [
    path('', api_root, name='api-root'),
]
