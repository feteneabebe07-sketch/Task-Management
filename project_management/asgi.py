import os

# Ensure Django settings are configured before importing Django/Channels
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Call get_asgi_application() to ensure Django apps are loaded before importing
# application code that may import models (like consumers)
http_app = get_asgi_application()

# Import routing after apps are ready to avoid AppRegistryNotReady
from project_manager import routing

application = ProtocolTypeRouter({
    'http': http_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})