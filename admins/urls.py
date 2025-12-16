# admins/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Page views
    path('', views.dashboard_view, name='dashboard'),
    path('departments/', views.departments_view, name='departments'),
    path('employees/', views.employees_view, name='employees'),
    path('projects/', views.projects_view, name='projects'),
    path('activity-log/', views.activity_log_view, name='activity_log'),

    
    # Protected API endpoints (require login)
    path('api/departments/create/', views.api_create_department, name='api_create_department'),
    path('api/departments/<int:department_id>/', views.api_get_department, name='api_get_department'),
    path('api/departments/<int:department_id>/update/', views.api_update_department, name='api_update_department'),
    path('api/employees/create/', views.api_create_employee, name='api_create_employee'),
    path('api/employees/<int:employee_id>/', views.api_get_employee, name='api_get_employee'),
    path('api/employees/<int:employee_id>/update/', views.api_update_employee, name='api_update_employee'),
    path('api/projects/create/', views.api_create_project, name='api_create_project'),
    path('api/projects/<int:project_id>/', views.api_get_project, name='api_get_project'),
    path('api/projects/<int:project_id>/team/', views.api_get_project_team, name='api_get_project_team'),
    path('api/projects/<int:project_id>/update/', views.api_update_project, name='api_update_project'),
    path('api/projects/assign-pm/', views.api_assign_pm, name='api_assign_pm'),
    path('api/tasks/create/', views.api_create_task, name='api_create_task'),
    path('api/announcements/send/', views.api_send_announcement, name='api_send_announcement'),
    path('api/dashboard/stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/dashboard/stats-details/<str:type>/', views.api_stats_details, name='api_stats_details'),
    path('api/notifications/unread-count/', views.api_notification_count, name='api_notification_count'),
path('pm-dashboard/', views.pm_dashboard_view, name='pm_dashboard'),
path('employee-dashboard/', views.employee_dashboard_view, name='employee_dashboard'),
path('employee/', views.developer_dashboard, name='dashboards'),


path('export/projects/', views.export_projects_csv, name='export_projects'),
path('export/employees/', views.export_employees_csv, name='export_employees'),
path('export/tasks/', views.export_tasks_csv, name='export_tasks'),
path('export/departments/', views.export_departments_csv, name='export_departments'),
path('export/activity/', views.export_recent_activity_csv, name='export_activity'),
]