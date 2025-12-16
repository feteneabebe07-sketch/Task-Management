from django.urls import path
from . import messages_api
from .views import (
    pm_dashboard, pm_projects, pm_project_detail,
    pm_tasks, pm_sprints, pm_team, pm_reports, get_user_websocket_url
)
from .views import (
    create_task_api, start_sprint_api, add_team_member_api,
    remove_team_member_api, approve_task_api, request_task_changes_api,
    get_available_employees_api, schedule_meeting_api,
    get_team_member_details, get_task_details_api, delete_task_api, update_task_api,pm_messages,get_available_employees_for_project
)

urlpatterns = [
    # Dashboard
    path('dashboard/', pm_dashboard, name='pm_dashboard'),
    
    # Project Management
    path('my_projects/', pm_projects, name='pm_projects'),
    path('projects/<int:project_id>/', pm_project_detail, name='pm_project_detail'),
    
    # Task Management
    path('tasks/', pm_tasks, name='pm_tasks'),
    
    # Sprint Management
    path('sprints/', pm_sprints, name='pm_sprints'),
    
    # Team Management
    path('team/', pm_team, name='pm_team'),
    
    # Reports
    path('reports/', pm_reports, name='pm_reports'),
    
    # API endpoints
    # Task APIs
    path('api/tasks/create/', create_task_api, name='create_task_api'),
    path('api/tasks/<int:task_id>/', get_task_details_api, name='get_task_details_api'),
    path('api/tasks/<int:task_id>/update/', update_task_api, name='update_task_api'),
    path('api/tasks/<int:task_id>/approve/', approve_task_api, name='approve_task_api'),
    path('api/tasks/<int:task_id>/request-changes/', request_task_changes_api, name='request_task_changes_api'),
    
    # Sprint APIs
    path('api/sprints/start/', start_sprint_api, name='start_sprint_api'),

    path('messages/', pm_messages, name='pm_messages'),
    path('get-ws-url/', get_user_websocket_url, name='get_user_websocket_url'),
    # Messages API endpoints
    path('api/messages/conversation/<int:user_id>/', messages_api.get_conversation_messages, name='get_conversation_messages'),
    path('api/messages/send/', messages_api.send_message_api, name='send_message_api'),
    path('api/messages/mark_read/<int:user_id>/', messages_api.mark_as_read_api, name='mark_as_read_api'),
    path('api/messages/unread_count/', messages_api.get_unread_count_api, name='get_unread_count_api'),
    path('api/messages/start_conversation/', messages_api.start_conversation_api, name='start_conversation_api'),
    path('api/messages/search_users/', messages_api.search_users_api, name='search_users_api'),
    # Team Management APIs
    path('api/team/add/', add_team_member_api, name='add_team_member_api'),
    path('api/team/remove/', remove_team_member_api, name='remove_team_member_api'),
    path('api/projects/<int:project_id>/available-employees/', get_available_employees_api, name='get_available_employees_api'),
    path('api/projects/<int:project_id>/team-member/<int:employee_id>/', get_team_member_details, name='get_team_member_details'),
    
    # Meeting APIs
    path('api/meetings/schedule/', schedule_meeting_api, name='schedule_meeting_api'),

    # API endpoints
    path('api/tasks/<int:task_id>/approve/', approve_task_api, name='approve_task_api'),
    path('api/tasks/<int:task_id>/request-changes/', request_task_changes_api, name='request_changes_api'),
    path('api/tasks/create/', create_task_api, name='create_task_api'),
    path('api/projects/<int:project_id>/available-employees/', get_available_employees_api, name='get_available_employees_api'),
    # Add this to the urlpatterns in urls.py
path('api/projects/<int:project_id>/available-employees-for-add/', get_available_employees_for_project, name='get_available_employees_for_add'),
]