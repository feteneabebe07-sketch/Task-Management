# views/pm_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test as _django_user_passes_test
from django.conf import settings
import logging
logger = logging.getLogger(__name__)
from django.utils.timesince import timesince
from django.db.models import F, Max
# Wrap user_passes_test to default to project's LOGIN_URL when '/login/' literal is used
def user_passes_test(test_func, login_url=None, **kwargs):
    # If code used the older placeholder '/login/', replace with configured LOGIN_URL
    if login_url == '/login/' or login_url is None:
        login_url = settings.LOGIN_URL
    return _django_user_passes_test(test_func, login_url=login_url, **kwargs)
from django.conf import settings
from django.http import JsonResponse
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta
from core.models import (
    User, EmployeeProfile, Department, Project, 
    Task, Sprint, ProjectMember, Message, Comment, 
    TimeLog, Notification, StandupUpdate
)
from .pm_helpers import calculate_member_task_statuses
def get_user_websocket_url(request):
    """Get WebSocket URL for the current user"""
    if request.is_secure():
        ws_scheme = "wss://"
    else:
        ws_scheme = "ws://"
    
    return f"{ws_scheme}{request.get_host()}/ws/messages/"

def is_project_manager(user):
    return user.is_authenticated and (user.role == 'pm' or user.role == 'admin')
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_dashboard(request):
    """PM Dashboard with multi-project support"""
    current_user = request.user
    today = timezone.now().date()
    
    # Get all projects managed by this PM
    managed_projects = Project.objects.filter(
        project_manager=current_user
    ).select_related('department').annotate(
        # Annotate each project with basic statistics
        total_tasks_count=Count('tasks'),
        completed_tasks_count=Count('tasks', filter=Q(tasks__status='done')),
        active_tasks_count=Count('tasks', filter=Q(tasks__status__in=['todo', 'in_progress', 'review'])),
        team_members_count=Count('members', distinct=True, filter=Q(members__is_active=True)),
        overdue_tasks_count=Count('tasks', filter=Q(tasks__due_date__lt=today, tasks__status__in=['todo', 'in_progress', 'review']))
    ).order_by('-status', '-created_at')
    
    # Get selected project from URL parameter or default
    selected_project_id = request.GET.get('project')
    if selected_project_id:
        try:
            selected_project = managed_projects.get(id=selected_project_id)
        except Project.DoesNotExist:
            selected_project = managed_projects.filter(status='active').first()
            if not selected_project:
                selected_project = managed_projects.first()
    else:
        # Default to first active project or first project
        selected_project = managed_projects.filter(status='active').first()
        if not selected_project:
            selected_project = managed_projects.first()
    
    context = {
        'user': current_user,
        'managed_projects': managed_projects,
        'selected_project': selected_project,
        'today': today,
    }
    
    # If there are projects, calculate overall statistics
    if managed_projects.exists():
        # Calculate project progress for each project
        for project in managed_projects:
            if project.total_tasks_count > 0:
                project.progress = int((project.completed_tasks_count / project.total_tasks_count) * 100)
            else:
                project.progress = 0
            
            # Calculate days remaining
            if project.due_date:
                days_remaining = (project.due_date - today).days
                project.days_remaining = max(0, days_remaining)
            else:
                project.days_remaining = None
        
        # Calculate overall statistics across all projects
        all_projects_stats = {
            'total_tasks': sum(p.total_tasks_count for p in managed_projects),
            'total_completed_tasks': sum(p.completed_tasks_count for p in managed_projects),
            'total_active_tasks': sum(p.active_tasks_count for p in managed_projects),
            'total_team_members': sum(p.team_members_count for p in managed_projects),
            'total_overdue_tasks': sum(p.overdue_tasks_count for p in managed_projects),
        }
        
        context['all_projects_stats'] = all_projects_stats
        
        # Projects by status for the pie chart
        projects_by_status = [
            {
                'name': 'Active',
                'count': managed_projects.filter(status='active').count(),
                'color_class': 'status-active'
            },
            {
                'name': 'Planning',
                'count': managed_projects.filter(status='planning').count(),
                'color_class': 'status-pending'
            },
            {
                'name': 'On Hold',
                'count': managed_projects.filter(status='on_hold').count(),
                'color_class': 'status-inactive'
            },
            {
                'name': 'Completed',
                'count': managed_projects.filter(status='completed').count(),
                'color_class': 'status-approved'
            }
        ]
        context['projects_by_status'] = projects_by_status
    
    # If a specific project is selected, get detailed information
    if selected_project:
        # Get team members for selected project - FIXED: Use distinct to avoid duplicates
        project_members = selected_project.members.filter(
            is_active=True
        ).select_related('employee__user').distinct()
        
        # Get actual team member count (not annotated)
        actual_team_members_count = project_members.count()
        
        # Prepare member data with task counts and status
        member_data = []
        for member in project_members:
            user = member.employee.user
            task_count = Task.objects.filter(
                project=selected_project,
                assigned_to=member.employee
            ).count()
            
            # Determine status based on recent activity
            last_task_update = Task.objects.filter(
                assigned_to=member.employee,
                project=selected_project
            ).aggregate(Max('updated_at'))['updated_at__max']
            
            if last_task_update and (today - last_task_update.date()).days <= 1:
                status = 'active'
                status_class = 'status-active'
                status_text = 'Active'
            else:
                status = 'inactive'
                status_class = 'status-inactive'
                status_text = 'Inactive'
            
            # Assign color class based on initials
            if user.first_name and user.last_name:
                initials = f"{user.first_name[0]}{user.last_name[0]}".upper()
            else:
                initials = user.username[:2].upper() if user.username else '??'
                
            color_index = sum(ord(c) for c in initials) % 5
            color_classes = [
                'from-dark-teal to-dark-cyan',
                'from-golden-orange to-vanilla-custard',
                'from-dark-cyan to-pearl-aqua',
                'from-rusty-spice to-oxidized-iron',
                'from-pearl-aqua to-vanilla-custard'
            ]
            color_class = color_classes[color_index]
            
            member_data.append({
                'member': member,
                'user_full_name': user.get_full_name(),
                'initials': initials,
                'task_count': task_count,
                'status': status,
                'status_class': status_class,
                'status_text': status_text,
                'color_class': color_class,
            })
        
        # Get tasks under review with detailed information
        review_tasks_data = []
        review_tasks = Task.objects.filter(
            project=selected_project,
            status='review'
        ).select_related('assigned_to__user')[:5]
        
        for task in review_tasks:
            # Calculate progress percentage
            time_logs = TimeLog.objects.filter(task=task)
            actual_hours = time_logs.aggregate(total=Sum('hours'))['total'] or 0
            progress_percentage = min(100, int((actual_hours / task.estimated_hours) * 100)) if task.estimated_hours and task.estimated_hours > 0 else 0
            
            # Get assignee info
            assignee_initials = ''
            assignee_name = 'Unassigned'
            if task.assigned_to and task.assigned_to.user:
                assignee_initials = f"{task.assigned_to.user.first_name[0]}{task.assigned_to.user.last_name[0]}".upper()
                assignee_name = task.assigned_to.user.get_full_name()
            
            # Priority class
            priority_classes = {
                'high': 'priority-high',
                'medium': 'priority-medium',
                'low': 'priority-low',
                'critical': 'priority-high'
            }
            priority_class = priority_classes.get(task.priority, 'priority-medium')
            
            # Format due date
            due_date_formatted = task.due_date.strftime('%b %d') if task.due_date else 'No deadline'
            
            review_tasks_data.append({
                'task': task,
                'initials': assignee_initials,
                'user_full_name': assignee_name,
                'progress': progress_percentage,
                'actual_hours': actual_hours,
                'estimated_hours': task.estimated_hours or 0,
                'priority_class': priority_class,
                'due_date_formatted': due_date_formatted,
            })
        
        # Get recent activity across all projects
        recent_activity = []
        
        # Recent task updates
        recent_task_updates = Task.objects.filter(
            project__in=managed_projects
        ).exclude(updated_at=F('created_at')).select_related('project', 'assigned_to__user').order_by('-updated_at')[:10]
        
        for task in recent_task_updates:
            # Handle potential None values
            project_name = task.project.name if task.project else 'Unknown Project'
            user_name = 'System'
            user_initials = 'S'
            if task.assigned_to and task.assigned_to.user:
                user_name = task.assigned_to.user.get_full_name()
                user_initials = f"{task.assigned_to.user.first_name[0]}{task.assigned_to.user.last_name[0]}"
            
            activity = {
                'type': 'task_update',
                'icon': 'fa-tasks',
                'icon_color': 'bg-dark-cyan/20 text-dark-cyan',
                'description': f'Task "{task.title[:30] if task.title else "Untitled"}..." updated',
                'time': timesince(task.updated_at),
                'project_name': project_name,
                'user_name': user_name,
                'user_initials': user_initials,
            }
            recent_activity.append(activity)
        
        # Get upcoming deadlines (next 7 days)
        upcoming_deadlines = []
        week_start = today
        week_end = today + timedelta(days=7)
        
        upcoming_tasks = Task.objects.filter(
            project=selected_project,
            due_date__range=[week_start, week_end],
            status__in=['todo', 'in_progress', 'review']
        ).select_related('assigned_to__user').order_by('due_date')[:6]
        
        for task in upcoming_tasks:
            days_until_due = (task.due_date - today).days
            upcoming_deadlines.append({
                'task': task,
                'title': task.title,
                'assigned_to': task.assigned_to,
                'days_until_due': days_until_due,
            })
        
        # Task status summary for selected project - FIXED: Calculate percentages
        task_status_summary_data = [
            {
                'name': 'To Do',
                'count': Task.objects.filter(project=selected_project, status='todo').count(),
                'color_class': 'status-pending'
            },
            {
                'name': 'In Progress',
                'count': Task.objects.filter(project=selected_project, status='in_progress').count(),
                'color_class': 'status-active'
            },
            {
                'name': 'Under Review',
                'count': Task.objects.filter(project=selected_project, status='review').count(),
                'color_class': 'status-inactive'
            },
            {
                'name': 'Completed',
                'count': Task.objects.filter(project=selected_project, status='done').count(),
                'color_class': 'status-approved'
            },
        ]
        
        # Calculate percentages for task status
        total_tasks_summary = sum(status['count'] for status in task_status_summary_data)
        for status in task_status_summary_data:
            if total_tasks_summary > 0:
                status['percentage'] = int((status['count'] / total_tasks_summary) * 100)
            else:
                status['percentage'] = 0
        
        # Task priority summary
        task_priority_summary = [
            {
                'name': 'High',
                'count': Task.objects.filter(project=selected_project, priority='high').count(),
                'class': 'priority-high',
                'bg_class': 'bg-rusty-spice'
            },
            {
                'name': 'Medium',
                'count': Task.objects.filter(project=selected_project, priority='medium').count(),
                'class': 'priority-medium',
                'bg_class': 'bg-golden-orange'
            },
            {
                'name': 'Low',
                'count': Task.objects.filter(project=selected_project, priority='low').count(),
                'class': 'priority-low',
                'bg_class': 'bg-dark-cyan'
            },
        ]
        
        # Calculate percentages for priority summary
        total_priority_tasks = sum(p['count'] for p in task_priority_summary)
        for priority in task_priority_summary:
            if total_priority_tasks > 0:
                priority['percentage'] = int((priority['count'] / total_priority_tasks) * 100)
            else:
                priority['percentage'] = 0
        
        # Get available employees for team management
        available_employees = EmployeeProfile.objects.filter(
            status='active',
            department=selected_project.department
        ).exclude(
            id__in=selected_project.members.filter(is_active=True).values_list('employee_id', flat=True)
        ).select_related('user', 'department')[:20]
        
        # Get active sprint
        active_sprint = Sprint.objects.filter(
            project=selected_project,
            status='active'
        ).first()
        
        # Get available sprints
        available_sprints = Sprint.objects.filter(
            project=selected_project,
            status__in=['planned', 'active']
        ).order_by('-start_date')[:5]
        
        # Calculate timeline percentage
        timeline_percentage = calculate_timeline_percentage(selected_project, today)
        
        # Add selected project detailed context - FIXED: Use correct values
        context.update({
            # Project statistics - use annotated values
            'total_tasks': selected_project.total_tasks_count,
            'completed_tasks': selected_project.completed_tasks_count,
            'active_tasks_count': selected_project.active_tasks_count,
            'team_members_count': actual_team_members_count,  # Use actual count, not annotated
            'overdue_count': selected_project.overdue_tasks_count,
            
            # Sprint information
            'active_sprint': active_sprint,
            'available_sprints': available_sprints,
            
            # Team information
            'project_members': project_members,
            'member_data': member_data,
            'available_employees': available_employees,
            
            # Task information
            'review_tasks': review_tasks_data,
            'task_status_summary': task_status_summary_data,  # Fixed variable name
            'task_priority_summary': task_priority_summary,
            
            # Recent activity
            'recent_activity_all_projects': recent_activity[:10],  # Limit to 10
            
            # Upcoming deadlines
            'upcoming_deadlines': upcoming_deadlines,
            
            # Additional project info for template
            'in_progress_tasks': Task.objects.filter(project=selected_project, status='in_progress').count(),
            'available_members': available_employees.count(),
            
            # Timeline and dates
            'days_remaining': selected_project.days_remaining if hasattr(selected_project, 'days_remaining') else None,
            'timeline_percentage': timeline_percentage,
        })
    
    return render(request, 'pm/dashboard.html', context)
# Helper function
def calculate_timeline_percentage(project, today):
    """Calculate project timeline percentage"""
    if not project.start_date or not project.due_date:
        return 0
    
    total_days = (project.due_date - project.start_date).days
    if total_days <= 0:
        return 100
    
    days_passed = (today - project.start_date).days
    if days_passed < 0:
        return 0
    elif days_passed > total_days:
        return 100
    
    return int((days_passed / total_days) * 100)

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_projects(request):
    """PM Projects List""" 
    current_user = request.user
    
    projects = Project.objects.filter(
        project_manager=current_user
    ).select_related('department').order_by('-created_at')
    
    # Get statistics for each project
    for project in projects:
        project.task_count = Task.objects.filter(project=project).count()
        project.completed_tasks = Task.objects.filter(
            project=project, status='done'
        ).count()
        project.active_tasks = Task.objects.filter(
            project=project, status__in=['todo', 'in_progress']
        ).count()
        
        if project.task_count > 0:
            project.progress_percentage = int((project.completed_tasks / project.task_count) * 100)
        else:
            project.progress_percentage = 0
        
        project.days_remaining_val = project.days_remaining()
    
    context = {
        'user': current_user,
        'projects': projects,
        'today': timezone.now().date(),
    }
    
    return render(request, 'pm/projects.html', context)

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_project_detail(request, project_id):
    """PM Project Detail View""" 
    project = get_object_or_404(
        Project.objects.select_related('department', 'project_manager'),
        id=project_id,
        project_manager=request.user
    )
    
    # Project tasks
    tasks = Task.objects.filter(project=project).select_related(
        'assigned_to__user', 'sprint'
    ).order_by('-priority', 'due_date')
    
    # Task statistics
    task_stats = {
        'total': tasks.count(),
        'todo': tasks.filter(status='todo').count(),
        'in_progress': tasks.filter(status='in_progress').count(),
        'review': tasks.filter(status='review').count(),
        'done': tasks.filter(status='done').count(),
    }
    
    # Team members
    team_members = ProjectMember.objects.filter(
        project=project, is_active=True
    ).select_related('employee__user')
    
    # Sprints
    sprints = Sprint.objects.filter(project=project).order_by('-start_date')
    
    # Recent activities
    recent_messages = Message.objects.filter(
        project=project
    ).select_related('sender').order_by('-created_at')[:10]
    
    context = {
        'project': project,
        'tasks': tasks,
        'task_stats': task_stats,
        'team_members': team_members,
        'sprints': sprints,
        'recent_messages': recent_messages,
        'today': timezone.now().date(),
    }
    
    return render(request, 'pm/project_detail.html', context)

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_tasks(request):
    """PM Tasks Management"""

    current_user = request.user
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # --------------------------------------------------
    # Projects managed by PM
    # --------------------------------------------------
    managed_projects = Project.objects.filter(project_manager=current_user)

    # Active project (used for assignment dropdown & context)
    active_project = managed_projects.filter(status='active').first() or managed_projects.first()
    request.active_project = active_project  # for context processors (optional)

    # --------------------------------------------------
    # Active project members (task assignment dropdown)
    # --------------------------------------------------
    member_data = []
    if active_project:
        project_members = ProjectMember.objects.filter(
            project=active_project,
            is_active=True
        ).select_related('employee__user')

        for member in project_members:
            user = member.employee.user
            initials = f"{user.first_name[:1]}{user.last_name[:1]}".upper()

            member_data.append({
                'member': member,
                'user_full_name': user.get_full_name(),
                'initials': initials,
            })

    # --------------------------------------------------
    # Base task queryset
    # --------------------------------------------------
    tasks = Task.objects.filter(
        project__in=managed_projects
    ).select_related(
        'project', 'assigned_to__user', 'sprint'
    ).order_by('-created_at')

    # --------------------------------------------------
    # Filters
    # --------------------------------------------------
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    project_filter = request.GET.get('project', '')
    search_query = request.GET.get('search', '')

    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if priority_filter:
        tasks = tasks.filter(priority=priority_filter)
    if project_filter:
        tasks = tasks.filter(project_id=project_filter)
    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(task_type__icontains=search_query)
        )

    # --------------------------------------------------
    # Statistics
    # --------------------------------------------------
    total_tasks_count = Task.objects.filter(project__in=managed_projects).count()

    active_tasks_count = Task.objects.filter(
        project__in=managed_projects,
        status__in=['todo', 'in_progress']
    ).count()

    overdue_tasks_count = Task.objects.filter(
        project__in=managed_projects,
        due_date__lt=today,
        status__in=['todo', 'in_progress', 'review']
    ).count()

    due_this_week_count = Task.objects.filter(
        project__in=managed_projects,
        due_date__range=[today, week_end],
        status__in=['todo', 'in_progress', 'review']
    ).count()

    high_priority_week_count = Task.objects.filter(
        project__in=managed_projects,
        due_date__range=[today, week_end],
        priority__in=['high', 'critical'],
        status__in=['todo', 'in_progress', 'review']
    ).count()

    completed_tasks_count = Task.objects.filter(
        project__in=managed_projects,
        status='done',
        completed_at__year=today.year,
        completed_at__month=today.month
    ).count()

    # Board counts (filtered view)
    todo_tasks_count = tasks.filter(status='todo').count()
    in_progress_tasks_count = tasks.filter(status='in_progress').count()
    review_tasks_count = tasks.filter(status='review').count()
    done_tasks_count = tasks.filter(status='done').count()

    # --------------------------------------------------
    # Recent Activity
    # --------------------------------------------------
    from core.models import Comment

    color_classes = [
        'dark-teal', 'dark-cyan', 'golden-orange',
        'rusty-spice', 'oxidized-iron', 'brown-red'
    ]

    recent_activity = []

    recent_comments = Comment.objects.filter(
        task__project__in=managed_projects
    ).select_related('user', 'task').order_by('-created_at')[:10]

    for comment in recent_comments:
        user = comment.user
        initials = (
            f"{user.first_name[:1]}{user.last_name[:1]}".upper()
            if user.first_name and user.last_name else "PM"
        )

        color_class = f"bg-{color_classes[user.id % len(color_classes)]}"

        recent_activity.append({
            'user_name': user.get_full_name(),
            'initials': initials,
            'color_class': color_class,
            'action': 'commented on',
            'task_title': comment.task.title,
            'details': comment.content[:50] + '...' if len(comment.content) > 50 else comment.content,
            'timestamp': comment.created_at,
        })

    recent_tasks = tasks.filter(updated_at__gte=today - timedelta(days=7))[:10]

    for task in recent_tasks:
        if task.updated_at > task.created_at + timedelta(minutes=5):
            user = task.assigned_to.user if task.assigned_to else None
            initials = (
                f"{user.first_name[:1]}{user.last_name[:1]}".upper()
                if user and user.first_name and user.last_name else "PM"
            )

            color_class = f"bg-{color_classes[task.id % len(color_classes)]}"

            recent_activity.append({
                'user_name': user.get_full_name() if user else 'System',
                'initials': initials,
                'color_class': color_class,
                'action': 'updated',
                'task_title': task.title,
                'details': f"status to {task.get_status_display()}",
                'timestamp': task.updated_at,
            })

    recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)

    # --------------------------------------------------
    # Subtask Progress
    # --------------------------------------------------
    for task in tasks:
        subtasks = getattr(task, 'subtasks', None)
        if subtasks:
            total = subtasks.count()
            completed = subtasks.filter(is_completed=True).count()
            task.subtasks_total = total
            task.subtasks_completed = completed
            task.progress = int((completed / total) * 100) if total > 0 else int(task.progress or 0)
        else:
            task.subtasks_total = 0
            task.subtasks_completed = 0
            task.progress = int(task.progress or 0)

    # --------------------------------------------------
    # Context
    # --------------------------------------------------
    context = {
        'tasks': tasks,
        'managed_projects': managed_projects,
        'active_project': active_project,
        'member_data': member_data,

        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'project_filter': project_filter,
        'today': today,

        'total_tasks_count': total_tasks_count,
        'active_tasks_count': active_tasks_count,
        'overdue_tasks_count': overdue_tasks_count,
        'due_this_week_count': due_this_week_count,
        'high_priority_week_count': high_priority_week_count,
        'completed_tasks_count': completed_tasks_count,

        'todo_tasks_count': todo_tasks_count,
        'in_progress_tasks_count': in_progress_tasks_count,
        'review_tasks_count': review_tasks_count,
        'done_tasks_count': done_tasks_count,

        'recent_activity': recent_activity[:5],
    }

    return render(request, 'pm/tasks.html', context)
def get_project_members_data(project):
    """Get formatted member data for a project"""
    if not project:
        return []
    
    project_members = ProjectMember.objects.filter(
        project=project,
        is_active=True
    ).select_related('employee__user')
    
    member_data = []
    for member in project_members:
        user = member.employee.user
        initials = f"{user.first_name[0]}{user.last_name[0]}" if user.first_name and user.last_name else '??'
        
        member_data.append({
            'member': member,
            'user_full_name': user.get_full_name(),
            'initials': initials,
            'role': member.get_role_display(),
        })
    
    return member_data



@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_sprints(request):
    """PM Sprints Management""" 
    current_user = request.user
    today = timezone.now().date()
    
    # Get all sprints from PM's projects
    managed_projects = Project.objects.filter(project_manager=current_user)
    sprints = Sprint.objects.filter(
        project__in=managed_projects
    ).select_related('project').order_by('-start_date')
    
    # Calculate sprint statistics
    for sprint in sprints:
        sprint_tasks = Task.objects.filter(sprint=sprint)
        sprint.total_tasks = sprint_tasks.count()
        sprint.completed_tasks = sprint_tasks.filter(status='done').count()
        sprint.in_progress_tasks = sprint_tasks.filter(status='in_progress').count()
        
        if sprint.total_tasks > 0:
            sprint.progress = int((sprint.completed_tasks / sprint.total_tasks) * 100)
        else:
            sprint.progress = 0
        
        if sprint.end_date > today:
            sprint.days_left = (sprint.end_date - today).days
        else:
            sprint.days_left = 0
    
    context = {
        'sprints': sprints,
        'managed_projects': managed_projects,
        'today': today,
    }
    
    return render(request, 'pm/sprints.html', context)



@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_reports(request):
    """PM Reports and Analytics""" 
    current_user = request.user
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Get PM's projects
    projects = Project.objects.filter(project_manager=current_user)
    
    # Project completion stats
    project_stats = []
    for project in projects:
        total_tasks = Task.objects.filter(project=project).count()
        completed_tasks = Task.objects.filter(project=project, status='done').count()
        overdue_tasks = Task.objects.filter(
            project=project,
            due_date__lt=today,
            status__in=['todo', 'in_progress', 'review']
        ).count()
        
        project_stats.append({
            'project': project,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'overdue_tasks': overdue_tasks,
            'progress': int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0,
        })
    
    # Team productivity (last 30 days)
    time_logs = TimeLog.objects.filter(
        date__gte=thirty_days_ago,
        task__project__in=projects
    ).values('employee__user__first_name', 'employee__user__last_name').annotate(
        total_hours=Sum('hours')
    ).order_by('-total_hours')
    
    # Task completion trend
    daily_completions = Task.objects.filter(
        project__in=projects,
        completed_at__gte=thirty_days_ago
    ).extra({'date': "date(completed_at)"}).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    context = {
        'project_stats': project_stats,
        'time_logs': time_logs,
        'daily_completions': list(daily_completions),
        'today': today,
        'thirty_days_ago': thirty_days_ago,
    }
    
    return render(request, 'pm/reports.html', context)

# API Views for AJAX operations
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def update_task_status(request):
    """Update task status via AJAX""" 
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        new_status = request.POST.get('status')
        
        try:
            task = Task.objects.get(id=task_id)
            
            # Verify the task belongs to PM's project
            if task.project.project_manager != request.user:
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            
            task.status = new_status
            if new_status == 'done':
                task.completed_at = timezone.now()
            task.save()
            
            # Create notification
            Notification.objects.create(
                user=task.assigned_to.user if task.assigned_to else task.project.project_manager,
                notification_type='task_updated',
                title=f'Task Updated: {task.title}',
                message=f'Task status changed to {task.get_status_display()}',
                related_id=task.id,
                related_type='task'
            )
            
            return JsonResponse({'success': True})
        except Task.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Task not found'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def add_team_member(request):
    """Add team member to project via AJAX""" 
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        employee_id = request.POST.get('employee_id')
        role = request.POST.get('role')
        
        try:
            project = Project.objects.get(id=project_id, project_manager=request.user)
            employee = EmployeeProfile.objects.get(id=employee_id)
            
            # Check if already a member
            existing_member = ProjectMember.objects.filter(
                project=project, employee=employee
            ).first()
            
            if existing_member:
                existing_member.is_active = True
                existing_member.role = role
                existing_member.save()
            else:
                ProjectMember.objects.create(
                    project=project,
                    employee=employee,
                    role=role,
                    is_active=True
                )
            
            # Create notification
            Notification.objects.create(
                user=employee.user,
                notification_type='task_assigned',
                title=f'Added to Project: {project.name}',
                message=f'You have been added to project {project.name} as {role}',
                related_id=project.id,
                related_type='project'
            )
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# views/pm_api_views.py
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
from datetime import datetime, timedelta
from core.models import (
    Task, Sprint, Project, ProjectMember,
    EmployeeProfile, User, Notification, Message
)

def is_project_manager(user):
    return user.is_authenticated and (user.role == 'pm' or user.role == 'admin')

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def create_task_api(request):
    """API endpoint to create a new task"""
    try:
        # Try to parse JSON data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            # Fallback to form data
            data = request.POST.dict()
        
        print(f"DEBUG: Received data: {data}")
        
        # Validate required fields
        required_fields = ['title', 'project_id', 'due_date', 'estimated_hours']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Get and validate project
        try:
            project = Project.objects.get(
                id=int(data['project_id']),
                project_manager=request.user
            )
        except (ValueError, Project.DoesNotExist):
            return JsonResponse({
                'success': False,
                'error': 'Invalid project or permission denied'
            })
        
        # Parse other required fields
        try:
            due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
            estimated_hours = float(data['estimated_hours'])
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid date or hours format'
            })
        
        # Handle assigned_to - Check if it's 'all' first
        assigned_to_value = data.get('assigned_to', '')
        print(f"DEBUG: assigned_to_value = '{assigned_to_value}'")
        
        # CASE 1: Assign to ALL team members
        if str(assigned_to_value).strip().lower() == 'all':
            print("DEBUG: Processing 'assign to all'")
            
            # Get all active project members
            project_members = ProjectMember.objects.filter(
                project=project,
                is_active=True
            ).select_related('employee__user')
            
            if not project_members.exists():
                return JsonResponse({
                    'success': False,
                    'error': 'No active team members in this project'
                })
            
            created_task_ids = []
            
            for member in project_members:
                try:
                    # Create individual task for each member
                    task = Task.objects.create(
                        title=data['title'],
                        description=data.get('description', ''),
                        project=project,
                        assigned_to=member.employee,  # CRITICAL: Use member.employee, not ID
                        task_type=data.get('task_type', 'feature'),
                        priority=data.get('priority', 'medium'),
                        estimated_hours=estimated_hours,
                        due_date=due_date,
                        status='todo',
                        progress=0,
                        actual_hours=0,
                        created_by=request.user
                    )
                    
                    created_task_ids.append(task.id)
                    
                    # Create notification
                    Notification.objects.create(
                        user=member.employee.user,
                        notification_type='task_assigned',
                        title=f'New Task: {task.title[:50]}',
                        message=f'You have been assigned: {task.title}',
                        related_id=task.id,
                        related_type='task'
                    )
                    
                except Exception as e:
                    print(f"DEBUG: Error creating task for member {member.id}: {e}")
                    continue
            
            return JsonResponse({
                'success': True,
                'message': f'Created {len(created_task_ids)} tasks for all team members',
                'task_ids': created_task_ids,
                'assigned_to_all': True,
                'members_count': len(created_task_ids)
            })
        
        # CASE 2: Assign to specific employee or leave unassigned
        assigned_employee = None
        if assigned_to_value and assigned_to_value != '' and str(assigned_to_value).strip().lower() != 'all':
            try:
                # Convert to integer
                employee_id = int(assigned_to_value)
                assigned_employee = EmployeeProfile.objects.get(id=employee_id)
                
                # Verify is project member
                if not ProjectMember.objects.filter(
                    project=project,
                    employee=assigned_employee,
                    is_active=True
                ).exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'Employee is not an active project member'
                    })
                    
            except ValueError:
                # Check if it's a special string value
                if str(assigned_to_value).strip().lower() == 'unassigned':
                    assigned_employee = None
                else:
                    return JsonResponse({
                        'success': False,
                        'error': f'Invalid employee ID: {assigned_to_value}'
                    })
            except EmployeeProfile.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Employee not found: {assigned_to_value}'
                })
        
        # CASE 3: Create single task (assigned or unassigned)
        task = Task.objects.create(
            title=data['title'],
            description=data.get('description', ''),
            project=project,
            assigned_to=assigned_employee,
            task_type=data.get('task_type', 'feature'),
            priority=data.get('priority', 'medium'),
            estimated_hours=estimated_hours,
            due_date=due_date,
            status='todo',
            progress=0,
            actual_hours=0,
            created_by=request.user
        )
        
        # Add to sprint if specified
        sprint_id = data.get('sprint_id')
        if sprint_id:
            try:
                sprint = Sprint.objects.get(id=int(sprint_id), project=project)
                task.sprint = sprint
                task.save()
            except (ValueError, Sprint.DoesNotExist):
                pass
        
        # Create notification if assigned
        if assigned_employee:
            Notification.objects.create(
                user=assigned_employee.user,
                notification_type='task_assigned',
                title=f'New Task: {task.title[:50]}',
                message=f'You have been assigned: {task.title}',
                related_id=task.id,
                related_type='task'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Task created successfully',
            'task_id': task.id,
            'task_title': task.title,
            'assigned_to_all': False
        })
        
    except Exception as e:
        print(f"DEBUG: Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def start_sprint_api(request):
    """API endpoint to start a new sprint"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['name', 'project_id', 'start_date', 'duration_weeks']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Get project
        project = get_object_or_404(
            Project,
            id=data['project_id'],
            project_manager=request.user
        )
        
        # Calculate end date
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        duration_days = int(data['duration_weeks']) * 7
        end_date = start_date + timedelta(days=duration_days)
        
        # Create sprint
        sprint = Sprint.objects.create(
            name=data['name'],
            goal=data.get('goal', ''),
            project=project,
            start_date=start_date,
            end_date=end_date,
            status='active',
            created_at=timezone.now(),
            updated_at=timezone.now()
        )
        
        # Add tasks to sprint if specified
        task_ids = data.get('task_ids', [])
        if task_ids:
            tasks = Task.objects.filter(
                id__in=task_ids,
                project=project,
                sprint__isnull=True  # Only add tasks not already in a sprint
            )
            tasks.update(sprint=sprint)
        
        # Notify team members
        team_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).select_related('employee__user')
        
        for member in team_members:
            Notification.objects.create(
                user=member.employee.user,
                notification_type='sprint',
                title=f'New Sprint Started: {sprint.name}',
                message=f'A new sprint "{sprint.name}" has started. Goal: {sprint.goal}',
                related_id=sprint.id,
                related_type='sprint'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Sprint started successfully!',
            'sprint_id': sprint.id,
            'sprint_name': sprint.name,
            'end_date': end_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def add_team_member_api(request):
    """API endpoint to add a team member to project"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['project_id', 'employee_id', 'role']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Get project
        project = get_object_or_404(
            Project,
            id=data['project_id'],
            project_manager=request.user
        )
        
        # Get employee
        employee = get_object_or_404(EmployeeProfile, id=data['employee_id'])
        
        # Check if already a member
        existing_member = ProjectMember.objects.filter(
            project=project,
            employee=employee
        ).first()
        
        if existing_member:
            # Reactivate if previously removed
            existing_member.is_active = True
            existing_member.role = data['role']
            existing_member.save()
            member = existing_member
        else:
            # Create new member
            member = ProjectMember.objects.create(
                project=project,
                employee=employee,
                role=data['role'],
                is_active=True,
                joined_at=timezone.now()
            )
        
        # Create notification for the employee
        Notification.objects.create(
            user=employee.user,
            notification_type='project',
            title=f'Added to Project: {project.name}',
            message=f'You have been added to project "{project.name}" as {member.get_role_display()}',
            related_id=project.id,
            related_type='project'
        )
        
        # Send message to the project channel
        Message.objects.create(
            sender=request.user,
            message_type='announcement',
            subject=f'New Team Member: {employee.user.get_full_name()}',
            content=f'{employee.user.get_full_name()} has joined the project as {member.get_role_display()}',
            project=project,
            is_read=False,
            created_at=timezone.now()
        )
        
        # Get updated team members for response
        team_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).select_related('employee__user')
        
        member_data = []
        for team_member in team_members:
            member_data.append({
                'id': team_member.employee.id,
                'name': team_member.employee.user.get_full_name(),
                'role': team_member.get_role_display(),
                'initials': f"{team_member.employee.user.first_name[0]}{team_member.employee.user.last_name[0]}" 
                if team_member.employee.user.first_name and team_member.employee.user.last_name 
                else team_member.employee.user.username[:2].upper(),
            })
        
        return JsonResponse({
            'success': True,
            'message': 'Team member added successfully!',
            'member_id': member.id,
            'team_members': member_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def remove_team_member_api(request):
    """API endpoint to remove a team member from project"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['project_id', 'employee_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Get project
        project = get_object_or_404(
            Project,
            id=data['project_id'],
            project_manager=request.user
        )
        
        # Get project member
        project_member = get_object_or_404(
            ProjectMember,
            project=project,
            employee_id=data['employee_id'],
            is_active=True
        )
        
        # Deactivate instead of delete
        project_member.is_active = False
        project_member.save()
        
        # Create notification for the employee
        Notification.objects.create(
            user=project_member.employee.user,
            notification_type='project',
            title=f'Removed from Project: {project.name}',
            message=f'You have been removed from project "{project.name}"',
            related_id=project.id,
            related_type='project'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Team member removed successfully!'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def approve_task_api(request, task_id=None):
    """API endpoint to approve a task (mark as done).
    Accepts `task_id` either from the URL (`/api/tasks/<id>/approve/`) or
    from the JSON body (`{'task_id': id}`)."""
    try:
        # Try to parse JSON body if present
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}

        # Determine effective task id: URL param takes precedence
        effective_task_id = task_id or data.get('task_id')
        if not effective_task_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: task_id'
            })

        # Get task
        task = get_object_or_404(Task, id=effective_task_id)
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })
        
        # Update task
        task.status = 'done'
        task.progress = 100
        task.completed_at = timezone.now()
        task.updated_at = timezone.now()
        task.save()
        
        # Create notification for assignee
        if task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to.user,
                notification_type='task_completed',
                title=f'Task Approved: {task.title}',
                message=f'Your task "{task.title}" has been approved and marked as completed',
                related_id=task.id,
                related_type='task'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Task approved successfully!',
            'task_id': task.id,
            'task_title': task.title
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def request_task_changes_api(request, task_id=None):
    """API endpoint to request changes on a task.
    Accepts `task_id` from the URL or from the JSON body.
    """
    try:
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}

        # Determine effective task id
        effective_task_id = task_id or data.get('task_id')

        # Validate required fields
        if not effective_task_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: task_id'
            })

        if 'feedback' not in data or not data.get('feedback'):
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: feedback'
            })

        # Get task
        task = get_object_or_404(Task, id=effective_task_id)
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })
        
        # Update task
        task.status = 'in_progress'  # Send back to in progress
        task.updated_at = timezone.now()
        task.save()
        
        # Create notification for assignee
        if task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to.user,
                notification_type='task_updated',
                title=f'Changes Requested: {task.title}',
                message=f'Changes requested on task "{task.title}": {data["feedback"]}',
                related_id=task.id,
                related_type='task'
            )
        
        # Create comment with feedback
        from core.models import Comment
        Comment.objects.create(
            task=task,
            user=request.user,
            content=f"PM requested changes: {data['feedback']}",
            created_at=timezone.now(),
            updated_at=timezone.now()
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Changes requested successfully!',
            'task_id': task.id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_available_employees_api(request, project_id):
    """API endpoint to get available employees for team management"""
    try:
        project = get_object_or_404(
            Project,
            id=project_id,
            project_manager=request.user
        )
        mode = request.GET.get('mode', 'available')
        
        if mode == 'members':
            # Return active project members (for task assignment)
            members = ProjectMember.objects.filter(
                project=project,
                is_active=True
            ).select_related('employee__user')
            
            employees_data = []
            for member in members:
                emp = member.employee
                employees_data.append({
                    'id': emp.id,
                    'name': emp.user.get_full_name(),
                    'email': emp.user.email,
                    'job_position': emp.job_position,
                    'department': emp.department.name if emp.department else 'No Department',
                    'role': member.role,
                })
            
            return JsonResponse({
                'success': True,
                'employees': employees_data,
                'allow_assign_all': True
            })
        
        elif mode == 'add_member':
            # For adding new members - exclude current members and the PM themselves
            current_members = ProjectMember.objects.filter(
                project=project,
                is_active=True
            ).values_list('employee_id', flat=True)
            
            # Get all active employees except current members and the PM
            available_employees = EmployeeProfile.objects.filter(
                status='active'
            ).exclude(
                id__in=current_members
            ).exclude(
                user=request.user  # Don't include the PM
            ).select_related('user', 'department').order_by('user__last_name')
            
            employees_data = []
            for employee in available_employees:
                employees_data.append({
                    'id': employee.id,
                    'employee_id': employee.employee_id,
                    'name': employee.user.get_full_name(),
                    'email': employee.user.email,
                    'job_position': employee.job_position,
                    'department': employee.department.name if employee.department else 'No Department',
                    'skills': employee.skills or 'No skills specified',
                    'user_role': employee.user.role if employee.user else None,
                })
            
            return JsonResponse({
                'success': True,
                'employees': employees_data,
                'project_name': project.name,
                'total_available': len(employees_data)
            })
        
        else:
            # Default: return available employees not already on the project
            current_members = ProjectMember.objects.filter(
                project=project,
                is_active=True
            ).values_list('employee_id', flat=True)
            
            available_employees = EmployeeProfile.objects.filter(
                status='active'
            ).exclude(
                id__in=current_members
            ).exclude(
                user=request.user  # Don't include the PM
            ).select_related('user', 'department').order_by('user__last_name')
            
            employees_data = []
            for employee in available_employees:
                employees_data.append({
                    'id': employee.id,
                    'name': employee.user.get_full_name(),
                    'email': employee.user.email,
                    'job_position': employee.job_position,
                    'department': employee.department.name if employee.department else 'No Department',
                    'skills': employee.skills or 'No skills specified'
                })
            
            return JsonResponse({
                'success': True,
                'employees': employees_data
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_available_employees_api(request, project_id):
    """API endpoint to get available employees for team management"""
    try:
        project = get_object_or_404(
            Project,
            id=project_id,
            project_manager=request.user
        )
        mode = request.GET.get('mode', 'available')

        if mode == 'members':
            # Return active project members (for task assignment)
            members = ProjectMember.objects.filter(
                project=project,
                is_active=True
            ).select_related('employee__user')

            employees_data = []
            for member in members:
                emp = member.employee
                employees_data.append({
                    'id': emp.id,
                    'name': emp.user.get_full_name(),
                    'email': emp.user.email,
                    'job_position': emp.job_position,
                    'department': emp.department.name if emp.department else 'No Department',
                    'role': member.role,
                })

            return JsonResponse({
                'success': True,
                'employees': employees_data,
                'allow_assign_all': True
            })

        # Default: return available employees not already on the project (for team management)
        # Get current team members
        current_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).values_list('employee_id', flat=True)
        
        # Get available employees (not in project, active status)
        available_employees = EmployeeProfile.objects.filter(
            status='active'
        ).exclude(
            id__in=current_members
        ).select_related('user', 'department').order_by('user__last_name')
        
        employees_data = []
        for employee in available_employees:
            employees_data.append({
                'id': employee.id,
                'name': employee.user.get_full_name(),
                'email': employee.user.email,
                'job_position': employee.job_position,
                'department': employee.department.name if employee.department else 'No Department',
                'skills': employee.skills or 'No skills specified'
            })
        
        return JsonResponse({
            'success': True,
            'employees': employees_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def schedule_meeting_api(request):
    """API endpoint to schedule a team meeting"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['title', 'date', 'time', 'project_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Get project
        project = get_object_or_404(
            Project,
            id=data['project_id'],
            project_manager=request.user
        )
        
        # Get team members
        team_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).select_related('employee__user')
        
        # Create message/announcement
        meeting_datetime = f"{data['date']} {data['time']}"
        message = Message.objects.create(
            sender=request.user,
            message_type='announcement',
            subject=f'Team Meeting: {data["title"]}',
            content=f'Team meeting scheduled for {meeting_datetime}. Agenda: {data.get("agenda", "General discussion")}',
            project=project,
            is_read=False,
            created_at=timezone.now()
        )
        
        # Add recipients
        for member in team_members:
            message.recipients.add(member.employee.user)
        
        # Create notifications
        for member in team_members:
            Notification.objects.create(
                user=member.employee.user,
                notification_type='project',
                title=f'Team Meeting Scheduled: {data["title"]}',
                message=f'Team meeting scheduled for {meeting_datetime}',
                related_id=message.id,
                related_type='message'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Team meeting scheduled successfully!',
            'meeting_title': data['title'],
            'meeting_datetime': meeting_datetime
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_projects(request):
    """PM Projects List"""
    current_user = request.user
    today = timezone.now().date()
    
    # Get projects managed by this PM
    projects = Project.objects.filter(
        project_manager=current_user
    ).select_related('department').order_by('-created_at')
    
    # Color classes for member avatars
    color_classes = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron', 'brown-red']
    
    # Get statistics for each project
    for project in projects:
        project.task_count = Task.objects.filter(project=project).count()
        project.completed_tasks = Task.objects.filter(
            project=project, status='done'
        ).count()
        project.active_tasks = Task.objects.filter(
            project=project, status__in=['todo', 'in_progress']
        ).count()
        
        if project.task_count > 0:
            project.progress_percentage = int((project.completed_tasks / project.task_count) * 100)
        else:
            project.progress_percentage = 0
        
        project.days_remaining_val = project.days_remaining()
        
        # Get team members for this project
        project_members = ProjectMember.objects.filter(
            project=project, is_active=True
        ).select_related('employee__user')[:6]
        
        project.team_members_count = ProjectMember.objects.filter(
            project=project, is_active=True
        ).count()
        
        # Prepare recent members data for avatars
        recent_members = []
        for i, member in enumerate(project_members[:4]):
            user = member.employee.user
            initials = f"{user.first_name[0]}{user.last_name[0]}" if user.first_name and user.last_name else user.username[:2].upper()
            color = color_classes[i % len(color_classes)]
            recent_members.append({
                'initials': initials,
                'color': color,
                'name': user.get_full_name()
            })
        
        project.recent_members = recent_members
    
    # Calculate project status statistics
    total_projects = projects.count()
    active_projects = projects.filter(status='active').count()
    completed_projects = projects.filter(status='completed').count()
    on_hold_planning_projects = projects.filter(status__in=['on_hold', 'planning']).count()
    
    context = {
        'user': current_user,
        'projects': projects,
        'today': today,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'on_hold_planning_projects': on_hold_planning_projects,
    }
    
    return render(request, 'pm/projects.html', context)

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_team(request):
    """PM Team Management"""
    current_user = request.user
    
    # Get all team members from PM's projects
    managed_projects = Project.objects.filter(project_manager=current_user)
    team_members = ProjectMember.objects.filter(
        project__in=managed_projects,
        is_active=True
    ).select_related('employee__user', 'project').distinct()
    
    # Get available employees (not in any of PM's projects)
    all_employees = EmployeeProfile.objects.filter(
        status='active'
    ).select_related('user', 'department').exclude(
        id__in=team_members.values_list('employee_id', flat=True)
    )
    
    # Color classes for avatars
    color_classes = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron', 'brown-red']
    
    # Project color mapping
    project_colors = {}
    for i, project in enumerate(managed_projects):
        project_colors[project.id] = color_classes[i % len(color_classes)]
    
    # Process team members data
    processed_members = []
    member_data_dict = {}
    
    # First, group by employee (since an employee can be in multiple projects)
    for member in team_members:
        employee = member.employee
        user = employee.user
        
        if employee.id not in member_data_dict:
            # Get user initials
            initials = f"{user.first_name[0]}{user.last_name[0]}" if user.first_name and user.last_name else user.username[:2].upper()
            
            # Get active tasks count
            active_tasks = Task.objects.filter(
                assigned_to=employee,
                status__in=['todo', 'in_progress', 'review']
            ).count()
            
            # Calculate workload percentage (max 10 tasks = 100%)
            workload_percentage = min(100, (active_tasks / 10) * 100) if active_tasks > 0 else 0
            
            # Determine workload status and color
            if active_tasks == 0:
                workload_status = 'available'
                workload_color = 'bg-dark-cyan'
            elif active_tasks <= 3:
                workload_status = 'available'
                workload_color = 'bg-dark-cyan'
            elif active_tasks <= 6:
                workload_status = 'busy'
                workload_color = 'bg-golden-orange'
            else:
                workload_status = 'away'
                workload_color = 'bg-rusty-spice'
            
            # Determine color class for avatar
            color_index = (employee.id % len(color_classes))
            color_class = f"bg-{color_classes[color_index]}"
            
            member_data_dict[employee.id] = {
                'employee_id': employee.id,
                'name': user.get_full_name(),
                'initials': initials,
                'email': user.email,
                'job_position': employee.job_position or 'Not specified',
                'role': member.role,  # Use the first role found
                'role_display': member.get_role_display(),
                'projects': [],
                'project_ids': [],
                'project_count': 0,
                'primary_project_id': member.project.id,  # Store first project ID for filtering
                'active_tasks': active_tasks,
                'workload_percentage': int(workload_percentage),
                'workload_status': workload_status,
                'workload_color': workload_color,
                'color_class': color_class,
                'employee': employee,
            }
        
        # Add project info to this employee
        project_info = {
            'id': member.project.id,
            'name': member.project.name,
            'initials': member.project.name[:2].upper(),
            'color': project_colors.get(member.project.id, 'gray-400'),
        }
        
        member_data_dict[employee.id]['projects'].append(project_info)
        member_data_dict[employee.id]['project_ids'].append(str(member.project.id))
        member_data_dict[employee.id]['project_count'] += 1
        
        # Update role if different (use the most common role or keep as is)
        # For simplicity, we'll keep the first role
    
    # Convert dict to list
    processed_members = list(member_data_dict.values())
    
    # Calculate statistics
    total_team_members = len(processed_members)
    
    # Count by role
    developers_count = sum(1 for m in processed_members if m['role'] in ['dev', 'developer'])
    designers_count = sum(1 for m in processed_members if m['role'] in ['designer', 'ui_ux'])
    qa_count = sum(1 for m in processed_members if m['role'] in ['qa', 'tester'])
    
    # Count available members (workload_status = 'available')
    available_members_count = sum(1 for m in processed_members if m['workload_status'] == 'available')
    available_developers = sum(1 for m in processed_members if m['role'] in ['dev', 'developer'] and m['workload_status'] == 'available')
    available_designers = sum(1 for m in processed_members if m['role'] in ['designer', 'ui_ux'] and m['workload_status'] == 'available')
    available_qa = sum(1 for m in processed_members if m['role'] in ['qa', 'tester'] and m['workload_status'] == 'available')
    
    context = {
        'team_members': processed_members,
        'available_employees': all_employees,
        'managed_projects': managed_projects,
        'total_team_members': total_team_members,
        'developers_count': developers_count,
        'designers_count': designers_count,
        'qa_count': qa_count,
        'available_members_count': available_members_count,
        'available_developers': available_developers,
        'available_designers': available_designers,
        'available_qa': available_qa,
    }
    
    return render(request, 'pm/team.html', context)
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_team_member_details(request, project_id, employee_id):
    """API endpoint to get team member details for a specific project"""
    try:
        # Get project
        project = get_object_or_404(
            Project,
            id=project_id,
            project_manager=request.user
        )
        
        # Get team member
        project_member = get_object_or_404(
            ProjectMember,
            project=project,
            employee_id=employee_id,
            is_active=True
        )
        
        # Get employee details
        employee = project_member.employee
        user = employee.user

        # Get tasks assigned to this employee for the project
        assigned_tasks_qs = Task.objects.filter(project=project, assigned_to=employee).order_by('due_date')
        assigned_tasks = []
        for t in assigned_tasks_qs:
            assigned_tasks.append({
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'status_display': t.get_status_display(),
                'progress': t.progress or 0,
                'estimated_hours': float(t.estimated_hours) if t.estimated_hours is not None else None,
                'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
            })

        return JsonResponse({
            'success': True,
            'employee_id': employee.id,
            'employee_name': user.get_full_name(),
            'project_id': project.id,
            'project_name': project.name,
            'role': project_member.role,
            'role_display': project_member.get_role_display(),
            'joined_at': project_member.joined_at.strftime('%Y-%m-%d') if project_member.joined_at else None,
            'email': user.email,
            'position': employee.job_position or 'Not specified',
            'department': employee.department.name if employee.department else 'No department',
            'assigned_tasks': assigned_tasks,
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

#tasks
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_task_details_api(request, task_id):
    """API endpoint to get task details"""
    try:
        task = get_object_or_404(Task, id=task_id)
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'task_title': task.title,
            'description': task.description,
            'project_name': task.project.name,
            'assignee': task.assigned_to.user.get_full_name() if task.assigned_to else None,
            'assignee_id': task.assigned_to.id if task.assigned_to else None,
            'priority': task.priority,
            'priority_display': task.get_priority_display(),
            'status': task.status,
            'status_display': task.get_status_display(),
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
            'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
            'actual_hours': float(task.actual_hours) if task.actual_hours else None,
            'progress': task.progress or 0,
            'task_type': task.task_type,
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M') if task.created_at else None,
            'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M') if task.completed_at else None,
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def delete_task_api(request):
    """API endpoint to delete a task"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if 'task_id' not in data or not data['task_id']:
            return JsonResponse({
                'success': False,
                'error': 'Missing required field: task_id'
            })
        
        # Get task
        task = get_object_or_404(Task, id=data['task_id'])
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })
        
        # Delete task
        task_id = task.id
        task_title = task.title
        task.delete()
        
        # Create notification for assignee if they exist
        if task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to.user,
                notification_type='task_updated',
                title=f'Task Deleted: {task_title}',
                message=f'Task "{task_title}" has been deleted',
                related_id=task_id,
                related_type='task'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Task deleted successfully!',
            'task_id': task_id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
@require_POST
def update_task_api(request, task_id):
    """API endpoint to update a task"""
    try:
        data = json.loads(request.body)
        
        # Get task
        task = get_object_or_404(Task, id=task_id)
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })
        
        # Update task fields
        if 'title' in data:
            task.title = data['title']
        if 'description' in data:
            task.description = data['description']
        if 'project_id' in data:
            project = get_object_or_404(Project, id=data['project_id'], project_manager=request.user)
            task.project = project
        if 'assigned_to' in data:
            if data['assigned_to']:  # This could be a string from the form
                try:
                    # Try to convert to int, handle 'all' case
                    if str(data['assigned_to']).lower() == 'all':
                        # 'all' is not valid for individual task update
                        pass
                    else:
                        employee = get_object_or_404(EmployeeProfile, id=int(data['assigned_to']))
                        task.assigned_to = employee
                except (ValueError, TypeError):
                    # If it's not a valid integer, set to None
                    task.assigned_to = None
            else:
                task.assigned_to = None
        if 'task_type' in data:
            task.task_type = data['task_type']
        if 'priority' in data:
            task.priority = data['priority']
        if 'due_date' in data:
            task.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
        if 'status' in data:
            old_status = task.status
            task.status = data['status']
            if data['status'] == 'done' and old_status != 'done':
                task.completed_at = timezone.now()
        if 'estimated_hours' in data:
            task.estimated_hours = float(data['estimated_hours']) if data['estimated_hours'] else 0
        if 'actual_hours' in data:
            task.actual_hours = float(data['actual_hours']) if data['actual_hours'] else 0
        if 'progress' in data:
            task.progress = int(data['progress']) if data['progress'] else 0
        
        task.updated_at = timezone.now()
        task.save()
        
        # Create notification for assignee if changed
        if 'assigned_to' in data and task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to.user,
                notification_type='task_updated',
                title=f'Task Updated: {task.title}',
                message=f'Task "{task.title}" has been updated',
                related_id=task.id,
                related_type='task'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Task updated successfully!',
            'task_id': task.id,
            'task_title': task.title
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_task_details_api(request, task_id):
    """API endpoint to get task details"""
    try:
        task = get_object_or_404(
            Task.objects.select_related('project', 'assigned_to__user'),
            id=task_id
        )
        
        # Verify the task belongs to PM's project
        if task.project.project_manager != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })
        
        # Get project members for assignee dropdown
        project_members = ProjectMember.objects.filter(
            project=task.project,
            is_active=True
        ).select_related('employee__user')
        
        assignee_options = []
        for member in project_members:
            assignee_options.append({
                'id': member.employee.id,
                'name': f"{member.employee.user.get_full_name()} ({member.get_role_display()})",
                'role': member.get_role_display()
            })
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'task_title': task.title,
            'description': task.description or '',
            'project_id': task.project.id,
            'project_name': task.project.name,
            'assignee_id': task.assigned_to.id if task.assigned_to else None,
            'assignee': task.assigned_to.user.get_full_name() if task.assigned_to else None,
            'task_type': task.task_type or 'feature',
            'priority': task.priority,
            'priority_display': task.get_priority_display(),
            'status': task.status,
            'status_display': task.get_status_display(),
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
            'estimated_hours': float(task.estimated_hours) if task.estimated_hours else 0,
            'actual_hours': float(task.actual_hours) if task.actual_hours else 0,
            'progress': task.progress or 0,
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M') if task.created_at else None,
            'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M') if task.updated_at else None,
            'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M') if task.completed_at else None,
            'assignee_options': assignee_options
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
# Add to existing views.py
from datetime import datetime, timedelta
import json
import redis
import os
import logging
from django.db.models import Q, Count, Max
from django.core.paginator import Paginator

# Redis connection
_redis_url = os.environ.get('REDIS_URL', 'redis://172.25.239.131:6379/0')
redis_client = redis.from_url(_redis_url)

@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def pm_messages(request):
    """PM Messages View"""
    current_user = request.user
    today = timezone.now()
    # Avatar color palette
    colors = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron', 'brown-red']
    
    # Get all direct messages for this PM
    messages = Message.objects.filter(
        Q(sender=current_user) | Q(recipients=current_user),
        message_type='direct'
    ).distinct().order_by('-created_at')
    
    # Group by conversation (other user)
    conversations = []
    
    # Get unique users from messages
    users_dict = {}
    for msg in messages:
        try:
            # Determine the other user in conversation
            if msg.sender == current_user:
                recipient = msg.recipients.first()
                other_user = recipient if recipient else None
            else:
                other_user = msg.sender

            if not other_user or other_user.id in users_dict:
                continue

            # Get employee profile
            employee = EmployeeProfile.objects.filter(user=other_user).first()

            # Get last message between users
            last_message = Message.objects.filter(
                Q(sender=current_user, recipients=other_user, message_type='direct') |
                Q(sender=other_user, recipients=current_user, message_type='direct')
            ).order_by('-created_at').first()

            # Count unread messages
            unread_count = Message.objects.filter(
                sender=other_user,
                recipients=current_user,
                is_read=False,
                message_type='direct'
            ).count()

            # Get user initials
            initials = get_user_initials(other_user)
            
            # Get color
            colors = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron', 'brown-red']
            color = f"bg-{colors[other_user.id % len(colors)]}"

            # Get last message content
            last_message_content = ""
            if last_message:
                last_message_content = last_message.content
                if len(last_message_content) > 50:
                    last_message_content = last_message_content[:50] + '...'

            # Create conversation entry
            conversations.append({
                'id': f"conv_{current_user.id}_{other_user.id}",
                'other_user': other_user,
                'name': other_user.get_full_name() or other_user.username,
                'initials': initials,
                'color': color,
                'job_position': employee.job_position if employee else 'Team Member',
                'last_message': last_message_content,
                'last_message_time': last_message.created_at if last_message else today,  # Make sure this is datetime
                'unread_count': unread_count,
                'unread': unread_count > 0,
                'is_online': False,  # You can implement online status if needed
            })

            users_dict[other_user.id] = True

        except Exception as e:
            logger.exception('Error processing message id=%s', getattr(msg, 'id', None))
            continue
    
    # Sort conversations by last message time
    conversations.sort(key=lambda x: x['last_message_time'], reverse=True)
    
    # Mark first conversation as active if there are any
    if conversations:
        conversations[0]['active'] = True
    
    # Get managed projects for team members
    managed_projects = Project.objects.filter(project_manager=current_user)
    
    # Get all team members from managed projects
    team_members = []
    for project in managed_projects:
        project_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).select_related('employee__user')
        
        for member in project_members:
            user = member.employee.user
            if user.id != current_user.id and not any(m['other_user'].id == user.id for m in conversations):
                team_members.append({
                    'id': user.id,
                    'get_full_name': user.get_full_name() or user.username,
                    'username': user.username,
                    'initials': get_user_initials(user),
                    'color': f"bg-{colors[user.id % len(colors)]}",
                    'employee_profile': {
                        'job_position': getattr(member.employee, 'job_position', None)
                    },
                    'project_name': project.name,
                })
    
    context = {
        'user': current_user,
        'conversations': conversations,
        'team_members': team_members,
        'today': today,
    }
    
    return render(request, 'pm/messages.html', context)
def get_user_initials(user):
    """Get user initials for avatar"""
    if user.get_full_name():
        names = user.get_full_name().split()
        if len(names) >= 2:
            return f"{names[0][0]}{names[1][0]}".upper()
    return user.username[:2].upper()

# Helper functions
def format_message_time(timestamp):
    """Format message timestamp for display"""
    if not timestamp:
        return ''
    
    now = timezone.now()
    diff = now - timestamp
    
    if diff.days == 0:
        if diff.seconds < 60:
            return 'Just now'
        elif diff.seconds < 3600:
            minutes = diff.seconds // 60
            return f'{minutes}m ago'
        else:
            hours = diff.seconds // 3600
            return f'{hours}h ago'
    elif diff.days == 1:
        return 'Yesterday'
    elif diff.days < 7:
        return f'{diff.days}d ago'
    else:
        return timestamp.strftime('%b %d')

def get_user_color(user_id):
    """Get consistent color for user avatar"""
    colors = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron', 'brown-red']
    return f"bg-{colors[user_id % len(colors)]}"




# Add this function to views.py (in the appropriate section)
@login_required
@user_passes_test(is_project_manager, login_url='/login/')
def get_available_employees_for_project(request, project_id):
    """API endpoint to get employees available to add to a specific project"""
    try:
        # Get project
        project = get_object_or_404(
            Project,
            id=project_id,
            project_manager=request.user
        )
        
        # Get current team members for this project
        current_members = ProjectMember.objects.filter(
            project=project,
            is_active=True
        ).values_list('employee_id', flat=True)
        
        # Get all active employees EXCEPT:
        # 1. Current project members (already in project)
        # 2. The current user (project manager - cannot add themselves)
        # 3. Any employee who is a project manager (optional, can be added if needed)
        
        available_employees = EmployeeProfile.objects.filter(
            status='active'
        ).exclude(
            id__in=current_members
        ).exclude(
            user=request.user  # Don't show the current PM
        ).select_related('user', 'department').order_by('user__last_name', 'user__first_name')
        
        employees_data = []
        for employee in available_employees:
            # Check if user has project manager role
            user_role = employee.user.role if employee.user else None
            is_pm = user_role in ['pm', 'admin']
            
            # We can add PMs as team members too, but let's note it
            employees_data.append({
                'id': employee.id,
                'employee_id': employee.employee_id,
                'name': employee.user.get_full_name(),
                'email': employee.user.email,
                'job_position': employee.job_position or 'Not specified',
                'department': employee.department.name if employee.department else 'No Department',
                'skills': employee.skills or 'No skills specified',
                'user_role': user_role,
                'is_pm': is_pm,
                'status': employee.status,
            })
        
        return JsonResponse({
            'success': True,
            'employees': employees_data,
            'project_name': project.name,
            'total_available': len(employees_data)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


