# urls.py
from django.urls import path
from . import views

app_name = 'employee'

urlpatterns = [
    # Dashboard and main views
    path('', views.developer_dashboard, name='dashboard'),
    path('dashboard/', views.developer_dashboard, name='dashboard'),
    
    # Task management
    path('tasks/', views.my_tasks, name='my_tasks'),
    path('tasks/<int:task_id>/update/', views.update_task_status, name='update_task_status'),
    path('tasks/<int:task_id>/', views.task_detail_modal, name='task_detail_modal'),
    path('tasks/<int:task_id>/detail/', views.task_detail, name='task_detail'),
    path('tasks/<int:task_id>/comments/add/', views.add_comment, name='add_comment'),
    path('tasks/<int:task_id>/subtasks/create/', views.create_subtask, name='create_subtask'),
    path('subtasks/<int:subtask_id>/update/', views.update_subtask, name='update_subtask'),
    path('tasks/<int:task_id>/log-time/', views.log_time, name='log_time'),
    
    # Time tracking
    path('time-tracking/', views.time_tracking, name='time_tracking'),
        path('time-tracking/start/', views.start_timer, name='start_timer'),
    path('time-tracking/stop/', views.stop_timer, name='stop_timer'),
    path('time-tracking/status/', views.get_timer_status, name='get_timer_status'),
    path('time-tracking/log-manual/', views.log_time_manual, name='log_time_manual'),
    path('time-tracking/delete/<int:log_id>/', views.delete_time_log, name='delete_time_log'),
    path('time-tracking/stats/', views.get_time_stats, name='get_time_stats'),
    
    # Sprint views
    path('sprint/', views.current_sprint, name='current_sprint'),
    
    # Standup
    path('standup/submit/', views.submit_standup, name='submit_standup'),
    
    # Messages - Make sure these URLs are correct
    path('messages/', views.messages_view, name='messages'),  # Changed from developer_dashboard
    path('messages/send/', views.send_direct_message, name='send_direct_message'),  # Changed name
    path('messages/send-form/', views.send_message, name='send_message'),
    path('messages/get-conversation/', views.get_conversation, name='get_conversation'),
    path('messages/get-new-messages/', views.get_new_messages, name='get_new_messages'),
    path('messages/mark-read/', views.mark_messages_read, name='mark_messages_read'),
    path('messages/unread-count/', views.get_unread_count, name='get_unread_count'),
    
    # Dashboard quick message (separate from messages page)
    path('dashboard/message/', views.send_quick_message, name='send_quick_message'),  # New URL for dashboard
    

    path('notifications/', views.notifications_view, name='notifications'),
    # Polling endpoint used by header JS: /employee/dashboard/api/notification-counts/
    path('dashboard/api/notification-counts/', views.notification_counts, name='notification_counts'),

    # Backwards-compatible API aliases used by templates
    path('api/messages/send/', views.send_direct_message, name='api_send_message'),
    path('api/tasks/<int:task_id>/', views.api_task_detail, name='api_task_detail'),
]
