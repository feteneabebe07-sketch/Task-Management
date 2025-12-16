# project_management/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Import your custom views
from admins import views as admin_views
from core import views as core_views

urlpatterns = [
    # Mount Django's built-in admin at the conventional '/admin/' path
    path('admin/', admin.site.urls),
    path('', include(('admins.urls', 'admins'), namespace='admins')),
    # Shorthand login route to support views that redirect to '/login/'
    path('login/', admin_views.employee_login_view, name='login'),
    path('api/', include(('core.api_urls', 'api'), namespace='api')),
    path('', include('project_manager.urls')),
    path('employee/', include(('employee.urls', 'employee'), namespace='employee')),
    # Custom authentication views
    path('accounts/', include([
        path('login/', admin_views.employee_login_view, name='login'),
        path('logout/', admin_views.logout_view, name='logout'),
    ])),
    # Temporary test endpoint to create users on hosted platforms that restrict shell access
    path('create-test-users/', core_views.create_test_users, name='create_test_users'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)