# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, Avg
from datetime import datetime, timedelta
from core.models import (
    User, EmployeeProfile, Task, Project, Sprint, 
    Message, Notification, StandupUpdate, TimeLog
)
from core.models import Comment
from core.models import Subtask
import json
def get_user_websocket_url(request):
    """Get WebSocket URL for the current user"""
    if request.is_secure():
        ws_scheme = "wss://"
    else:
        ws_scheme = "ws://"
    
    return f"{ws_scheme}{request.get_host()}/ws/messages/"
@login_required
def developer_dashboard(request):
    """Developer dashboard view"""
    # Get employee profile
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    
    # Today's date
    today = timezone.now().date()
    
    # Today's tasks
    today_tasks = Task.objects.filter(
        assigned_to=employee,
        due_date=today,
        status__in=['todo', 'in_progress']
    ).select_related('project').prefetch_related('files')
    
    # Pending tasks
    pending_tasks = Task.objects.filter(
        assigned_to=employee,
        status__in=['todo', 'in_progress']
    ).exclude(due_date=today)
    
    # Due this week
    week_end = today + timedelta(days=7)
    due_this_week = Task.objects.filter(
        assigned_to=employee,
        due_date__range=[today, week_end],
        status__in=['todo', 'in_progress']
    ).count()
    
    # Get current sprint
    current_sprint = Sprint.objects.filter(
        project__members__employee=employee,
        status='active'
    ).first()
    
    # Calculate sprint progress
    sprint_progress = 0
    if current_sprint:
        total_points = current_sprint.total_points()
        completed_points = current_sprint.completed_points()
        if total_points > 0:
            sprint_progress = int((completed_points / total_points) * 100)
    
    # Workload calculation
    weekly_hours = calculate_weekly_hours(employee)
    sprint_hours = calculate_sprint_hours(employee, current_sprint)
    monthly_hours = calculate_monthly_hours(employee)
    
    # Determine workload status
    total_hours = weekly_hours.get('percentage', 0)
    if total_hours >= 90:
        workload_status = "Overloaded"
    elif total_hours >= 70:
        workload_status = "Heavy"
    elif total_hours >= 40:
        workload_status = "Manageable"
    else:
        workload_status = "Light"
    
    # Upcoming deadlines
    upcoming_deadlines = get_upcoming_deadlines(employee)
    
    # Recent messages
    recent_messages = Message.objects.filter(
        Q(recipients=request.user) | Q(sender=request.user)
    ).distinct().select_related('sender', 'task')[:3]
    
    # Today's standup (if exists)
    standup = StandupUpdate.objects.filter(
        employee=employee,
        date=today
    ).first()
    
    # Prepare context
    context = {
        'employee': employee,
        'today_tasks': today_tasks,
        'today_tasks_count': today_tasks.count(),
        'in_progress_tasks_count': today_tasks.filter(status='in_progress').count(),
        'pending_tasks_count': pending_tasks.count(),
        'due_this_week_count': due_this_week,
        'sprint_progress': sprint_progress,
        'workload_percentage': weekly_hours.get('percentage', 0),
        'workload_status': workload_status,
        'weekly_hours': weekly_hours,
        'sprint_hours': sprint_hours,
        'monthly_hours': monthly_hours,
        'upcoming_deadlines': upcoming_deadlines,
        'recent_messages': recent_messages,
        'standup': standup,
        'unread_notifications': Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).count(),
        'unread_messages': Message.objects.filter(
            recipients=request.user,
            is_read=False
        ).count(),
    }
    # Determine project managers and team members for quick messaging
    try:
        projects = Project.objects.filter(
            Q(members__employee=employee) | Q(tasks__assigned_to=employee)
        ).distinct()

        pm_user_ids = [p.project_manager.id for p in projects if p.project_manager]
        project_managers = User.objects.filter(id__in=pm_user_ids).distinct()

        team_members_qs = Project.objects.filter(id__in=projects.values_list('id', flat=True))
        team_members = User.objects.filter(
            employee_profile__project_memberships__project__in=projects
        ).exclude(id=request.user.id).distinct()

        # serialize minimal info for template
        context['project_managers'] = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in project_managers]
        context['team_members'] = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in team_members]
    except Exception:
        context['project_managers'] = []
        context['team_members'] = []
    
    return render(request, 'employee/dashboard.html', context)

@login_required
def submit_standup(request):
    """Handle standup submission"""
    if request.method == 'POST':
        employee = get_object_or_404(EmployeeProfile, user=request.user)
        today = timezone.now().date()
        
        standup, created = StandupUpdate.objects.update_or_create(
            employee=employee,
            date=today,
            defaults={
                'yesterday_work': request.POST.get('yesterday_work'),
                'today_plan': request.POST.get('today_plan'),
                'blockers': request.POST.get('blockers', ''),
            }
        )
        
        # Create notification for project manager
        if employee.department and employee.department.manager:
            Notification.objects.create(
                user=employee.department.manager,
                notification_type='standup',
                title=f'Standup Update from {employee.get_full_name()}',
                message=f'{employee.get_full_name()} submitted their daily standup.',
                related_id=employee.id,
                related_type='employeeprofile'
            )
        
        return redirect('employee:dashboard')
    
    return redirect('employee:dashboard')

@login_required
def update_task_status(request, task_id):
    """Update task status"""
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, assigned_to__user=request.user)
        new_status = request.POST.get('status')
        
        if new_status in dict(Task.STATUS_CHOICES).keys():
            task.status = new_status
            if new_status == 'done':
                task.completed_at = timezone.now()
                task.progress = 100
            elif new_status == 'in_progress':
                task.start_date = timezone.now().date()
                task.progress = 50
            
            task.save()

            # Create notification for task creator
            if task.created_by:
                Notification.objects.create(
                    user=task.created_by,
                    notification_type='task_updated',
                    title=f'Task {task.get_status_display()}',
                    message=f'{request.user.get_full_name()} changed task "{task.title}" to {task.get_status_display()}.',
                    related_id=task.id,
                    related_type='task'
                )
            # Save any uploaded files (screenshots) attached during submission
            try:
                uploaded_files = []
                if request.FILES:
                    # support multiple files under the 'files' field
                    uploaded_files = request.FILES.getlist('files') or request.FILES.getlist('file') or []
                for f in uploaded_files:
                    TaskFile.objects.create(task=task, file=f, name=getattr(f, 'name', str(f)), uploaded_by=request.user)
            except Exception:
                # best-effort: don't break submission if file save fails
                pass
            # If this was an AJAX request, return JSON so frontend can update in-place
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})

            return redirect('employee:dashboard')

@login_required
def task_detail_modal(request, task_id):
    """Return task detail for modal view"""
    task = get_object_or_404(Task, id=task_id, assigned_to__user=request.user)
    return render(request, 'partials/task_modal.html', {'task': task})

# Helper functions
def calculate_weekly_hours(employee):
    """Calculate weekly hours"""
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    time_logs = TimeLog.objects.filter(
        employee=employee,
        date__range=[week_start, week_end]
    )
    
    total_hours = time_logs.aggregate(total=Sum('hours'))['total'] or 0
    standard_hours = 40
    
    return {
        'current': total_hours,
        'total': standard_hours,
        'percentage': min(int((total_hours / standard_hours) * 100), 100) if standard_hours > 0 else 0
    }

def calculate_sprint_hours(employee, sprint):
    """Calculate sprint hours"""
    if not sprint:
        return {'current': 0, 'total': 0, 'percentage': 0}
    
    time_logs = TimeLog.objects.filter(
        employee=employee,
        task__sprint=sprint
    )
    
    total_hours = time_logs.aggregate(total=Sum('hours'))['total'] or 0
    estimated_hours = Task.objects.filter(
        assigned_to=employee,
        sprint=sprint
    ).aggregate(total=Sum('estimated_hours'))['total'] or 0
    
    return {
        'current': total_hours,
        'total': estimated_hours,
        'percentage': min(int((total_hours / estimated_hours) * 100), 100) if estimated_hours > 0 else 0
    }

def calculate_monthly_hours(employee):
    """Calculate monthly hours"""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    time_logs = TimeLog.objects.filter(
        employee=employee,
        date__gte=month_start
    )
    
    total_hours = time_logs.aggregate(total=Sum('hours'))['total'] or 0
    standard_hours = 160  # 40 hours/week * 4 weeks
    
    return {
        'current': total_hours,
        'total': standard_hours,
        'percentage': min(int((total_hours / standard_hours) * 100), 100) if standard_hours > 0 else 0
    }

def get_upcoming_deadlines(employee):
    """Get upcoming deadlines"""
    today = timezone.now().date()
    deadlines = []
    
    # Task deadlines
    tasks = Task.objects.filter(
        assigned_to=employee,
        due_date__gt=today,
        status__in=['todo', 'in_progress']
    ).order_by('due_date')[:5]
    
    for task in tasks:
        days_remaining = (task.due_date - today).days
        if days_remaining <= 3:
            color = 'red'
        elif days_remaining <= 7:
            color = 'orange'
        else:
            color = 'blue'
        
        deadlines.append({
            'title': task.title,
            'date': task.due_date,
            'days_remaining': days_remaining,
            'color': color
        })
    
    return deadlines

# Other views for navigation
@login_required
def my_tasks(request):
    """My tasks view"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    tasks = Task.objects.filter(assigned_to=employee).select_related('project', 'project__project_manager').prefetch_related('files')

    # Dates for filtering
    today = timezone.now().date()
    week_end = today + timedelta(days=7)

    # Pre-computed filters moved from template into view
    review_count = tasks.filter(status='review').count()
    week_tasks = tasks.filter(due_date__range=[today, week_end], status__in=['todo', 'in_progress'])
    week_tasks_count = week_tasks.count()

    today_priority_tasks = tasks.filter(priority='high', due_date=today, status__in=['todo', 'in_progress'])

    # Status counts
    status_qs = tasks.values('status').annotate(count=Count('id'))
    status_counts = {item['status']: item['count'] for item in status_qs}

    # Time logged today
    time_logged_today = TimeLog.objects.filter(employee=employee, date=today).aggregate(total=Sum('hours'))['total'] or 0

    # Time distribution this week by project
    week_start = today
    time_logs_week = TimeLog.objects.filter(employee=employee, date__range=[week_start, week_end])
    total_hours_this_week = time_logs_week.aggregate(total=Sum('hours'))['total'] or 0
    # Aggregate by project name
    proj_hours = (
        time_logs_week.values('task__project__name')
        .annotate(hours=Sum('hours'))
        .order_by('-hours')
    )
    time_distribution_list = []
    for p in proj_hours:
        hours = p.get('hours') or 0
        project_name = p.get('task__project__name') or 'Other'
        percentage = (float(hours) / float(total_hours_this_week) * 100) if total_hours_this_week else 0
        time_distribution_list.append({'project': project_name, 'hours': hours, 'percentage': round(percentage, 1)})

    # Today's standup
    standup = StandupUpdate.objects.filter(employee=employee, date=today).first()

    # Workflow steps for template
    workflow_steps = ['todo', 'in_progress', 'review', 'done']

    # Build a JS-friendly data structure for the front-end modal and interactions
    task_data = {}
    for t in tasks:
        # compute subtask counts and adjust progress if subtasks exist
        try:
            subtasks_qs = t.subtasks.all()
            subt_count = subtasks_qs.count()
            subt_completed = subtasks_qs.filter(is_completed=True).count()
            t.subtasks_count = subt_count
            t.subtasks_completed = subt_completed
            if subt_count > 0:
                # derive progress from subtasks
                t.progress = int((subt_completed / subt_count) * 100)
        except Exception:
            t.subtasks_count = 0
            t.subtasks_completed = 0
            t.progress = int(t.progress or 0)

        project = t.project
        project_manager = project.project_manager if project else None

        attachments_list = []
        for f in t.files.all():
            attachments_list.append({
                'id': f.id,
                'name': getattr(f, 'name', '') or getattr(f, 'file', '').split('/')[-1],
                'size': '',
                'type': 'file'
                , 'url': getattr(f, 'file', None).url if getattr(f, 'file', None) else ''
            })

        # Serialize comments for modal
        comments_list = []
        for c in Comment.objects.filter(task=t).select_related('user').order_by('created_at'):
            comments_list.append({
                'id': c.id,
                'author': c.user.get_full_name() if getattr(c, 'user', None) else str(c.user) if getattr(c, 'user', None) else 'Unknown',
                'content': c.content,
                'created_at': c.created_at.strftime('%b %d, %Y %H:%M') if getattr(c, 'created_at', None) else ''
            })

        # Build simple activity feed (time logs + subtasks)
        activity_list = []
        for tl in TimeLog.objects.filter(task=t).order_by('-date')[:5]:
            activity_list.append({
                'type': 'timelog',
                'date': tl.date.strftime('%b %d, %Y') if getattr(tl, 'date', None) else '',
                'hours': float(tl.hours) if getattr(tl, 'hours', None) else 0,
                'note': getattr(tl, 'description', '')
            })
        try:
            subtasks_qs = t.subtasks.all() if hasattr(t, 'subtasks') else []
            subtasks_count = subtasks_qs.count() if hasattr(subtasks_qs, 'count') else 0
            subtasks_completed = subtasks_qs.filter(is_completed=True).count() if hasattr(subtasks_qs, 'filter') else 0
            for st in (subtasks_qs.order_by('-created_at')[:5] if hasattr(subtasks_qs, 'order_by') else []):
                activity_list.append({
                    'type': 'subtask',
                    'id': st.id,
                    'title': st.title,
                    'is_completed': getattr(st, 'is_completed', False),
                    'created_at': st.created_at.strftime('%b %d, %Y') if getattr(st, 'created_at', None) else ''
                })
        except Exception:
            subtasks_count = 0
            subtasks_completed = 0
            pass

        # compute subtask-inferred progress if subtasks exist
        try:
            if subtasks_count > 0:
                sub_progress = int((subtasks_completed / subtasks_count) * 100)
            else:
                sub_progress = int(t.progress or 0)
        except Exception:
            sub_progress = int(t.progress or 0)
        except Exception:
            pass

        task_data[t.id] = {
            'id': t.id,
            'title': t.title,
            'project': project.name if project else '',
            'projectManager': project_manager.get_full_name() if project_manager else '',
            'type': t.task_type,
            'priority': t.priority,
            'status': t.status,
            'progress': sub_progress,
            'description': t.description or '',
            'projectDescription': project.description if project else '',
            'hours_estimated': float(t.estimated_hours) if t.estimated_hours else 0,
            'hours_actual': float(t.actual_hours) if t.actual_hours else 0,
            'due_date': str(t.due_date) if t.due_date else '',
            'attachments': t.files.count(),
            'attachments_list': attachments_list,
            'comments': comments_list,
            'activity': activity_list,
            'subtasks_count': subtasks_count,
            'subtasks_completed': subtasks_completed,
            'created': t.created_at.strftime('%b %d, %Y') if t.created_at else '',
            'assigned_to': t.assigned_to.get_full_name() if t.assigned_to else ''
        }

    task_data_json = json.dumps(task_data)

    return render(request, 'employee/my-tasks.html', {
        'tasks': tasks,
        'task_data_json': task_data_json,
        'current_date': today,
        'week_end': week_end,
        'review_count': review_count,
        'week_tasks': week_tasks,
        'week_tasks_count': week_tasks_count,
        'today_priority_tasks': today_priority_tasks,
        'status_counts': status_counts,
        'time_logged_today': time_logged_today,
        'time_distribution_list': time_distribution_list,
        'total_hours_this_week': total_hours_this_week,
        'standup': standup,
        'workflow_steps': workflow_steps,
    })

@login_required
def current_sprint(request):
    """Current sprint view"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    sprint = Sprint.objects.filter(
        project__members__employee=employee,
        status='active'
    ).first()
    
    if sprint:
        tasks = Task.objects.filter(
            assigned_to=employee,
            sprint=sprint
        ).order_by('priority')
    else:
        tasks = Task.objects.none()
    
    return render(request, 'current_sprint.html', {'sprint': sprint, 'tasks': tasks})

@login_required
def time_tracking(request):
    """Time tracking view"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    time_logs = TimeLog.objects.filter(employee=employee).order_by('-date')
    return render(request, 'time_tracking.html', {'time_logs': time_logs})


@login_required
def send_quick_message(request):
    """Handle quick message form from developer dashboard"""
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            # Create a message authored by the current user
            Message.objects.create(
                sender=request.user,
                message_type='announcement',
                content=content,
                is_read=False,
                created_at=timezone.now()
            )

    # Redirect back to dashboard (or referer if present)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('employee:dashboard')
# employee_portal/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, Avg
from datetime import datetime, timedelta
from core.models import (
    User, EmployeeProfile, Task, Project, Sprint, 
    Message, Notification, StandupUpdate, TimeLog,
    Comment, Subtask, TaskFile
)

@login_required
def task_detail(request, task_id):
    """View task details"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    task = get_object_or_404(Task, id=task_id, assigned_to=employee)
    
    # Get subtasks
    subtasks = Subtask.objects.filter(task=task).order_by('created_at')
    
    # Get comments
    comments = Comment.objects.filter(task=task).order_by('created_at')
    
    # Get time logs
    time_logs = TimeLog.objects.filter(task=task).order_by('-date')
    
    context = {
        'task': task,
        'subtasks': subtasks,
        'comments': comments,
        'time_logs': time_logs,
    }
    
    # If a dedicated template isn't available, redirect back to tasks list
    # and let the client open the modal for this task using the `open` query param.
    return redirect(f"{request.build_absolute_uri('/employee/tasks/').rstrip('/')}/?open={task_id}")


@login_required
def api_task_detail(request, task_id):
    """Return JSON details for a task used by dashboard JS."""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    task = get_object_or_404(Task, id=task_id, assigned_to=employee)

    # simple color mapping for priority/status
    priority_map = {
        'high': 'golden-orange',
        'medium': 'pearl-aqua',
        'low': 'dark-teal'
    }
    status_map = {
        'todo': 'golden-orange',
        'in_progress': 'dark-cyan',
        'review': 'pearl-aqua',
        'done': 'dark-teal'
    }

    data = {
        'id': task.id,
        'title': task.title,
        'description': task.description or '',
        'priority_color': priority_map.get(getattr(task, 'priority', ''), 'golden-orange'),
        'status_color': status_map.get(getattr(task, 'status', ''), 'golden-orange'),
        'project': task.project.name if task.project else 'General',
        'due_date': task.due_date.strftime('%b %d, %Y') if task.due_date else 'No due date',
        'progress': int(getattr(task, 'progress', 0) or 0),
        'attachments': [],
    }

    return JsonResponse(data)


@login_required
def add_comment(request, task_id):
    """Add a comment to a task (expects JSON POST or form POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    task = get_object_or_404(Task, id=task_id, assigned_to__user=request.user)

    # parse JSON body if provided
    content = ''
    try:
        if request.body:
            data = json.loads(request.body.decode('utf-8'))
            content = data.get('content', '').strip()
    except Exception:
        content = ''

    # fallback to form data
    if not content:
        content = request.POST.get('content', '').strip()

    if not content:
        return JsonResponse({'error': 'Empty comment'}, status=400)

    comment = Comment.objects.create(task=task, user=request.user, content=content)

    # Notify task creator (best-effort)
    try:
        if task.created_by:
            Notification.objects.create(
                user=task.created_by,
                notification_type='comment',
                title=f'New comment on "{task.title}"',
                message=f'{request.user.get_full_name()}: {content[:140]}',
                related_id=comment.id,
                related_type='comment'
            )
    except Exception:
        pass

    return JsonResponse({
        'id': comment.id,
        'author': request.user.get_full_name() or request.user.username,
        'content': comment.content,
        'created_at': comment.created_at.strftime('%b %d, %Y %H:%M')
    })


@login_required
def create_subtask(request, task_id):
    """Create a subtask for a task (AJAX POST expected)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    task = get_object_or_404(Task, id=task_id, assigned_to__user=request.user)

    title = ''
    description = ''
    try:
        if request.body:
            data = json.loads(request.body.decode('utf-8'))
            title = data.get('title', '').strip()
            description = data.get('description', '').strip()
    except Exception:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)

    sub = Subtask.objects.create(task=task, title=title, description=description)

    # Return the created subtask info for the frontend to append
    return JsonResponse({
        'id': sub.id,
        'title': sub.title,
        'is_completed': sub.is_completed,
        'created_at': sub.created_at.strftime('%b %d, %Y %H:%M')
    })


@login_required
def update_subtask(request, subtask_id):
    """Update a subtask (toggle completion or edit). Returns counts and progress."""
    if request.method not in ('POST', 'PUT'):
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    try:
        sub = Subtask.objects.select_related('task', 'task__assigned_to__user').get(id=subtask_id)
    except Subtask.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    # allow task assignee, project manager, or admins to update subtasks
    allowed = False
    try:
        if sub.task.assigned_to and sub.task.assigned_to.user == request.user:
            allowed = True
        elif sub.task.project and sub.task.project.project_manager and sub.task.project.project_manager == request.user:
            allowed = True
        elif getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', '') == 'pm':
            allowed = True
    except Exception:
        allowed = False

    if not allowed:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # parse JSON or form
    is_completed = None
    try:
        if request.body:
            data = json.loads(request.body.decode('utf-8'))
            if 'is_completed' in data:
                is_completed = bool(data.get('is_completed'))
    except Exception:
        pass

    if is_completed is None:
        # fallback to form data
        if 'is_completed' in request.POST:
            is_completed = request.POST.get('is_completed') in ('1', 'true', 'True')

    if is_completed is not None:
        sub.is_completed = is_completed
        sub.save()

    # recompute counts and progress
    try:
        task = sub.task
        subtasks_qs = task.subtasks.all()
        total = subtasks_qs.count()
        completed = subtasks_qs.filter(is_completed=True).count()
        progress = int((completed / total) * 100) if total > 0 else int(task.progress or 0)
    except Exception:
        total = 0
        completed = 0
        progress = int(task.progress or 0)

    return JsonResponse({
        'success': True,
        'subtask_id': sub.id,
        'is_completed': sub.is_completed,
        'subtasks_total': total,
        'subtasks_completed': completed,
        'progress': progress
    })

@login_required
def log_time(request, task_id):
    """Log time for a task"""
    if request.method == 'POST':
        employee = get_object_or_404(EmployeeProfile, user=request.user)
        task = get_object_or_404(Task, id=task_id, assigned_to=employee)
        
        hours = request.POST.get('hours')
        description = request.POST.get('description', '')
        date = request.POST.get('date', timezone.now().date())
        
        if hours:
            TimeLog.objects.create(
                task=task,
                employee=employee,
                date=date,
                hours=hours,
                description=description
            )
            
            # Update task actual hours
            total_hours = TimeLog.objects.filter(task=task).aggregate(total=Sum('hours'))['total'] or 0
            task.actual_hours = total_hours
            task.save()
            
            return redirect('employee:task_detail', task_id=task_id)
    
    return redirect('employee:dashboard')

@login_required
def messages_view(request):
    """View messages"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    
    # Get received messages
    received_messages = Message.objects.filter(
        recipients=request.user
    ).order_by('-created_at')
    
    # Get sent messages
    sent_messages = Message.objects.filter(
        sender=request.user
    ).order_by('-created_at')
    
    # Mark messages as read when viewing
    received_messages.filter(is_read=False).update(is_read=True)
    
    context = {
        'received_messages': received_messages,
        'sent_messages': sent_messages,
    }
    
    return render(request, 'employee/messages.html', context)

@login_required
def send_message(request):
    """Send a message"""
    if request.method == 'POST':
        content = request.POST.get('content')
        recipient_ids = request.POST.getlist('recipients')
        
        if content and recipient_ids:
            message = Message.objects.create(
                sender=request.user,
                message_type='direct',
                content=content,
                subject=request.POST.get('subject', '')
            )
            
            # Add recipients
            recipients = User.objects.filter(id__in=recipient_ids)
            message.recipients.set(recipients)
            
            # Create notifications for recipients
            for recipient in recipients:
                Notification.objects.create(
                    user=recipient,
                    notification_type='message',
                    title='New Message',
                    message=f'You have a new message from {request.user.get_full_name()}',
                    related_id=message.id,
                    related_type='message'
                )
            
            return redirect('employee:messages')
    
    return redirect('employee:messages')

@login_required
def notifications_view(request):
    """View notifications"""
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')
    
    # Mark as read when viewing
    notifications.filter(is_read=False).update(is_read=True)
    
    context = {
        'notifications': notifications,
    }
    
    return render(request, 'employee/notifications.html', context)



# views.py (corrected - remove duplicates)
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, Avg, F
from datetime import datetime, timedelta
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import (
    User, EmployeeProfile, Task, Project, Sprint, 
    Message, Notification, StandupUpdate, TimeLog,
    Comment, Subtask, TaskFile
)

# ... (keep all other views above until time tracking section)

@login_required
def time_tracking(request):
    """Time tracking view with timer functionality"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    today = timezone.now().date()
    
    # Get today's time logs
    today_time_logs = TimeLog.objects.filter(
        employee=employee,
        date=today
    ).select_related('task', 'task__project').order_by('-date', '-created_at')
    
    # Calculate today's total hours
    today_total = today_time_logs.aggregate(total=Sum('hours'))['total'] or 0
    
    # Get tasks assigned to the employee that are not done
    available_tasks = Task.objects.filter(
        assigned_to=employee,
        status__in=['todo', 'in_progress']
    ).select_related('project').order_by('due_date')
    
    # Get current active task (if any)
    current_task = available_tasks.first() if available_tasks.exists() else None
    
    # Get current timer session from session
    timer_session = request.session.get('timer_session', None)
    if timer_session:
        # Check if timer is still valid (not older than 24 hours)
        timer_start = datetime.fromisoformat(timer_session['start_time'])
        if (timezone.now() - timer_start).total_seconds() > 86400:
            # Timer expired, remove it
            del request.session['timer_session']
            timer_session = None
    
    # Get weekly time logs for chart
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    
    weekly_data = []
    for day in week_days:
        day_logs = TimeLog.objects.filter(
            employee=employee,
            date=day
        ).aggregate(total=Sum('hours'))['total'] or 0
        weekly_data.append({
            'day': day.strftime('%a'),
            'date': day.strftime('%Y-%m-%d'),
            'hours': float(day_logs)
        })
    
    # Get project-wise time distribution for the week
    project_time = TimeLog.objects.filter(
        employee=employee,
        date__range=[week_start, week_start + timedelta(days=6)]
    ).values('task__project__name').annotate(
        total_hours=Sum('hours')
    ).order_by('-total_hours')
    
    context = {
        'today_time_logs': today_time_logs,
        'today_total_hours': round(today_total, 2),
        'available_tasks': available_tasks,
        'current_task': current_task,
        'timer_session': timer_session,
        'weekly_data': weekly_data,
        'project_time': project_time,
        'unread_notifications': Notification.objects.filter(user=request.user, is_read=False).count(),
        'unread_messages': Message.objects.filter(recipients=request.user, is_read=False).count(),
    }
    
    return render(request, 'employee/time_tracking.html', context)


@login_required
@require_POST
def start_timer(request):
    """Start timer for a task"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    task_id = request.POST.get('task_id')
    
    if not task_id:
        return JsonResponse({'success': False, 'error': 'Task ID required'})
    
    task = get_object_or_404(Task, id=task_id, assigned_to=employee)
    
    # Stop any existing timer
    if 'timer_session' in request.session:
        # Auto-save the previous timer
        timer_data = request.session['timer_session']
        elapsed = (timezone.now() - datetime.fromisoformat(timer_data['start_time'])).total_seconds() / 3600
        if elapsed > 0:
            TimeLog.objects.create(
                task_id=timer_data['task_id'],
                employee=employee,
                date=datetime.fromisoformat(timer_data['start_time']).date(),
                hours=round(elapsed, 2),
                description=timer_data.get('description', '')
            )
    
    # Start new timer
    timer_session = {
        'task_id': task.id,
        'task_title': task.title,
        'start_time': timezone.now().isoformat(),
        'description': request.POST.get('description', '')
    }
    
    request.session['timer_session'] = timer_session
    request.session.modified = True
    
    # Update task status to in_progress if it's todo
    if task.status == 'todo':
        task.status = 'in_progress'
        task.start_date = timezone.now().date()
        task.save()
    
    return JsonResponse({
        'success': True,
        'task_id': task.id,
        'task_title': task.title,
        'start_time': timer_session['start_time']
    })


@login_required
@require_POST
def stop_timer(request):
    """Stop current timer and save time log"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    
    if 'timer_session' not in request.session:
        return JsonResponse({'success': False, 'error': 'No active timer'})
    
    timer_data = request.session['timer_session']
    
    # Calculate elapsed time
    start_time = datetime.fromisoformat(timer_data['start_time'])
    elapsed_seconds = (timezone.now() - start_time).total_seconds()
    elapsed_hours = round(elapsed_seconds / 3600, 2)
    
    if elapsed_hours <= 0:
        return JsonResponse({'success': False, 'error': 'Timer duration too short'})
    
    task = get_object_or_404(Task, id=timer_data['task_id'], assigned_to=employee)
    
    # Create time log
    time_log = TimeLog.objects.create(
        task=task,
        employee=employee,
        date=start_time.date(),
        hours=elapsed_hours,
        description=timer_data.get('description', 'Working on task')
    )
    
    # Update task's actual hours
    # Normalize to float to avoid Decimal/float arithmetic issues
    try:
        current_actual = float(task.actual_hours or 0)
    except Exception:
        current_actual = 0.0
    new_actual = current_actual + float(elapsed_hours)
    task.actual_hours = new_actual
    task.save()
    
    # Update task progress based on time spent
    if task.estimated_hours:
        try:
            estimated = float(task.estimated_hours)
            if estimated > 0:
                progress_percentage = min(int((new_actual / estimated) * 100), 100)
                task.progress = progress_percentage
                task.save()
        except Exception:
            # leave progress unchanged on conversion errors
            pass
    
    # Clear timer session
    del request.session['timer_session']
    request.session.modified = True
    
    # Calculate today's total
    today = timezone.now().date()
    today_total = TimeLog.objects.filter(
        employee=employee,
        date=today
    ).aggregate(total=Sum('hours'))['total'] or 0
    
    return JsonResponse({
        'success': True,
        'time_log_id': time_log.id,
        'task_title': task.title,
        'hours': elapsed_hours,
        'description': time_log.description,
        'date': start_time.date().strftime('%b %d, %Y'),
        'today_total': round(today_total, 2)
    })


@login_required
def get_timer_status(request):
    """Get current timer status"""
    timer_session = request.session.get('timer_session', None)
    
    if timer_session:
        start_time = datetime.fromisoformat(timer_session['start_time'])
        elapsed_seconds = (timezone.now() - start_time).total_seconds()
        
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        
        return JsonResponse({
            'active': True,
            'task_id': timer_session['task_id'],
            'task_title': timer_session['task_title'],
            'start_time': timer_session['start_time'],
            'elapsed': {
                'hours': hours,
                'minutes': minutes,
                'seconds': seconds,
                'total_hours': round(elapsed_seconds / 3600, 2)
            },
            'formatted_time': f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        })
    
    return JsonResponse({'active': False})


@login_required
@require_POST
def log_time_manual(request):
    """Log time manually"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    
    task_id = request.POST.get('task')
    date_str = request.POST.get('date')
    hours = request.POST.get('hours')
    description = request.POST.get('description', '')
    
    if not all([task_id, date_str, hours]):
        return JsonResponse({'success': False, 'error': 'Missing required fields'})
    
    try:
        task = get_object_or_404(Task, id=task_id, assigned_to=employee)
        date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
        hours_float = float(hours)
        
        # Validate hours
        if hours_float <= 0 or hours_float > 24:
            return JsonResponse({'success': False, 'error': 'Invalid hours value'})
        
        # Create time log
        time_log = TimeLog.objects.create(
            task=task,
            employee=employee,
            date=date,
            hours=hours_float,
            description=description
        )
        
        # Update task's actual hours
        task.actual_hours = (task.actual_hours or 0) + hours_float
        task.save()
        
        # Update task progress based on time spent
        if task.estimated_hours and task.estimated_hours > 0:
            progress_percentage = min(int((task.actual_hours / task.estimated_hours) * 100), 100)
            task.progress = progress_percentage
            task.save()
        
        # Calculate today's total
        today = timezone.now().date()
        today_total = TimeLog.objects.filter(
            employee=employee,
            date=today
        ).aggregate(total=Sum('hours'))['total'] or 0
        
        return JsonResponse({
            'success': True,
            'time_log_id': time_log.id,
            'task_title': task.title,
            'project': task.project.name if task.project else 'General',
            'date': date.strftime('%b %d, %Y'),
            'hours': hours_float,
            'description': description,
            'today_total': round(today_total, 2)
        })
        
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid data format'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def delete_time_log(request, log_id):
    """Delete a time log entry"""
    if request.method != 'DELETE':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
    
    try:
        time_log = TimeLog.objects.get(id=log_id, employee__user=request.user)
        
        # Update task's actual hours
        task = time_log.task
        task.actual_hours = max(0, (task.actual_hours or 0) - time_log.hours)
        task.save()
        
        # Delete the time log
        time_log.delete()
        
        # Calculate today's total
        today = timezone.now().date()
        today_total = TimeLog.objects.filter(
            employee__user=request.user,
            date=today
        ).aggregate(total=Sum('hours'))['total'] or 0
        
        return JsonResponse({
            'success': True,
            'today_total': round(today_total, 2)
        })
        
    except TimeLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Time log not found'}, status=404)


@login_required
def get_time_stats(request):
    """Get time statistics for charts and reports"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    today = timezone.now().date()
    
    # Weekly stats
    week_start = today - timedelta(days=today.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    
    weekly_stats = []
    for date in week_dates:
        day_total = TimeLog.objects.filter(
            employee=employee,
            date=date
        ).aggregate(total=Sum('hours'))['total'] or 0
        
        weekly_stats.append({
            'day': date.strftime('%a'),
            'date': date.strftime('%Y-%m-%d'),
            'hours': float(day_total)
        })
    
    # Monthly stats (last 30 days)
    month_ago = today - timedelta(days=30)
    monthly_stats = TimeLog.objects.filter(
        employee=employee,
        date__gte=month_ago,
        date__lte=today
    ).values('date').annotate(
        total_hours=Sum('hours')
    ).order_by('date')
    
    # Project-wise distribution for current month
    month_start = today.replace(day=1)
    project_distribution = TimeLog.objects.filter(
        employee=employee,
        date__gte=month_start
    ).values(
        'task__project__name',
        'task__project__id'
    ).annotate(
        total_hours=Sum('hours'),
        task_count=Count('task', distinct=True)
    ).order_by('-total_hours')
    
    # Daily average
    total_days = TimeLog.objects.filter(employee=employee).dates('date', 'day').distinct().count()
    total_hours = TimeLog.objects.filter(employee=employee).aggregate(total=Sum('hours'))['total'] or 0
    daily_avg = round(total_hours / total_days, 2) if total_days > 0 else 0
    
    return JsonResponse({
        'success': True,
        'weekly_stats': weekly_stats,
        'monthly_stats': list(monthly_stats),
        'project_distribution': list(project_distribution),
        'daily_average': daily_avg,
        'total_hours_logged': float(total_hours),
        'total_days_logged': total_days
    })


@login_required
def messages_view(request):
    """Messages view"""
    employee = get_object_or_404(EmployeeProfile, user=request.user)
    
    # Get all users except current user
    available_users = User.objects.filter(
        is_active=True
    ).exclude(id=request.user.id).select_related('employee_profile')
    
    # Get user's tasks for message context
    user_tasks = Task.objects.filter(
        assigned_to=employee,
        status__in=['todo', 'in_progress']
    ).order_by('-due_date')
    
    # Get conversations (users who have sent or received messages from current user)
    # Get sent messages
    sent_messages = Message.objects.filter(sender=request.user).values_list('recipients', flat=True)
    
    # Get received messages
    received_messages = Message.objects.filter(recipients=request.user).values_list('sender', flat=True)
    
    # Combine and get unique user IDs
    conversation_user_ids = set(list(sent_messages) + list(received_messages))
    
    # Get conversation details
    conversations = []
    for user_id in conversation_user_ids:
        try:
            user = User.objects.get(id=user_id)
            
            # Get last message between these users
            last_message = Message.objects.filter(
                Q(sender=request.user, recipients=user) |
                Q(sender=user, recipients=request.user)
            ).order_by('-created_at').first()
            
            # Count unread messages from this user
            unread_count = Message.objects.filter(
                sender=user,
                recipients=request.user,
                is_read=False
            ).count()
            
            # Get color for avatar based on user ID
            colors = ['bg-golden-orange', 'bg-dark-cyan', 'bg-rusty-spice', 'bg-pearl-aqua', 'bg-dark-teal']
            color_index = user.id % len(colors)
            
            conversations.append({
                'id': f"conv_{request.user.id}_{user.id}",
                'other_user': user,
                'name': user.get_full_name() or user.username,
                'initials': get_user_initials(user),
                'color': colors[color_index],
                'last_message': last_message.content if last_message else 'Start a conversation',
                'last_message_time': last_message.created_at if last_message else timezone.now(),
                'task_tag': f"#task-{last_message.task.id}" if last_message and last_message.task else None,
                'tag_color': 'bg-dark-teal bg-opacity-10 text-dark-teal' if last_message else '',
                'unread': unread_count > 0,
                'active': False  # Will be set based on current view
            })
        except User.DoesNotExist:
            continue
    
    # Sort conversations by last message time
    conversations.sort(key=lambda x: x['last_message_time'], reverse=True)
    
    # Mark first conversation as active if there are any
    if conversations:
        conversations[0]['active'] = True
    
    context = {
        'available_users': available_users,
        'user_tasks': user_tasks,
        'conversations': conversations,
        'unread_notifications': Notification.objects.filter(user=request.user, is_read=False).count(),
        'unread_messages': Message.objects.filter(recipients=request.user, is_read=False).count(),
    }
    # Also provide project managers and team members for the "no conversations" quick form
    try:
        projects = Project.objects.filter(
            Q(members__employee=employee) | Q(tasks__assigned_to=employee)
        ).distinct()

        pm_user_ids = [p.project_manager.id for p in projects if p.project_manager]
        project_managers = User.objects.filter(id__in=pm_user_ids).distinct()

        team_members = User.objects.filter(
            employee_profile__project_memberships__project__in=projects
        ).exclude(id=request.user.id).distinct()
    except Exception:
        project_managers = User.objects.none()
        team_members = User.objects.none()

    context['project_managers'] = project_managers
    context['team_members'] = team_members

    return render(request, 'employee/messages.html', context)


def get_user_initials(user):
    """Get user initials for avatar"""
    if user.get_full_name():
        names = user.get_full_name().split()
        if len(names) >= 2:
            return f"{names[0][0]}{names[1][0]}".upper()
    return user.username[:2].upper()


@login_required
def get_conversation(request):
    """Get conversation messages"""
    user_id = request.GET.get('user_id')
    conversation_id = request.GET.get('conversation_id')
    
    if not user_id:
        return JsonResponse({'success': False, 'error': 'User ID required'})
    
    try:
        other_user = User.objects.get(id=user_id)
        
        # Get messages between users
        messages = Message.objects.filter(
            Q(sender=request.user, recipients=other_user) |
            Q(sender=other_user, recipients=request.user)
        ).order_by('created_at')
        
        # Get user info
        user_info = {
            'id': other_user.id,
            'name': other_user.get_full_name() or other_user.username,
            'role': other_user.employee_profile.job_position if hasattr(other_user, 'employee_profile') else other_user.get_role_display(),
            'color': get_user_color(other_user.id),
            'avatar_color': get_user_color(other_user.id),
            'initials': get_user_initials(other_user),
        }
        
        # Format messages
        formatted_messages = []
        for message in messages:
            formatted_messages.append({
                'id': message.id,
                'content': message.content,
                'sender_id': message.sender.id,
                'sender_name': message.sender.get_full_name() or message.sender.username,
                'sender_initials': get_user_initials(message.sender),
                'initials': get_user_initials(message.sender),
                'avatar_color': get_user_color(message.sender.id),
                'created_at': message.created_at.isoformat(),
                'is_sent': message.sender.id == request.user.id,
                'task_tag': f"#task-{message.task.id}" if message.task else None,
                'is_read': message.is_read,
            })
        
        return JsonResponse({
            'success': True,
            'user': user_info,
            'messages': formatted_messages
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})


def get_user_color(user_id):
    """Get consistent color for user avatar"""
    colors = ['bg-golden-orange', 'bg-dark-cyan', 'bg-rusty-spice', 'bg-pearl-aqua', 'bg-dark-teal']
    return colors[user_id % len(colors)]


@login_required
def send_direct_message(request):
    """Send a direct message to another user"""
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        content = request.POST.get('content', '').strip()
        task_id = request.POST.get('task')
        
        if not content:
            return JsonResponse({'success': False, 'error': 'Message content required'})
        
        try:
            recipient = User.objects.get(id=recipient_id)
            
            # Create message
            message = Message.objects.create(
                sender=request.user,
                message_type='direct',
                content=content,
            )
            
            # Add recipient
            message.recipients.add(recipient)
            
            # Add task if specified
            if task_id:
                try:
                    task = Task.objects.get(id=task_id, assigned_to__user=request.user)
                    message.task = task
                    message.save()
                except Task.DoesNotExist:
                    pass
            
            # Create notification for recipient
            Notification.objects.create(
                user=recipient,
                notification_type='message',
                title='New Message',
                message=f'You have a new message from {request.user.get_full_name()}',
                related_id=message.id,
                related_type='message'
            )
            
            # Format response
            formatted_message = {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.isoformat(),
                'sender_initials': get_user_initials(request.user),
                'initials': get_user_initials(request.user),
                'avatar_color': get_user_color(request.user.id),
            }
            
            return JsonResponse({
                'success': True,
                'message': formatted_message,
                'recipient_id': recipient.id,
                'recipient_name': recipient.get_full_name() or recipient.username,
                'new_conversation': not Message.objects.filter(
                    Q(sender=request.user, recipients=recipient) |
                    Q(sender=recipient, recipients=request.user)
                ).exclude(id=message.id).exists()
            })
            
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Recipient not found'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def get_new_messages(request):
    """Get new messages since last check"""
    conversation_id = request.GET.get('conversation_id')
    last_checked = request.GET.get('last_checked')
    
    if not conversation_id:
        return JsonResponse({'success': False, 'error': 'Conversation ID required'})
    
    try:
        # Parse conversation ID to get user IDs
        parts = conversation_id.split('_')
        if len(parts) == 3 and parts[0] == 'conv':
            user1_id = int(parts[1])
            user2_id = int(parts[2])
            
            # Determine other user
            other_user_id = user2_id if request.user.id == user1_id else user1_id
            other_user = User.objects.get(id=other_user_id)
            
            # Get new messages
            query = Message.objects.filter(
                sender=other_user,
                recipients=request.user,
                is_read=False
            )
            
            if last_checked:
                try:
                    last_checked_date = datetime.fromisoformat(last_checked.replace('Z', '+00:00'))
                    query = query.filter(created_at__gt=last_checked_date)
                except ValueError:
                    pass
            
            new_messages = query.order_by('created_at')
            
            # Format messages
            formatted_messages = []
            for message in new_messages:
                formatted_messages.append({
                    'id': message.id,
                    'content': message.content,
                    'sender_id': message.sender.id,
                    'sender_name': message.sender.get_full_name() or message.sender.username,
                    'sender_initials': get_user_initials(message.sender),
                    'initials': get_user_initials(message.sender),
                    'avatar_color': get_user_color(message.sender.id),
                    'created_at': message.created_at.isoformat(),
                    'is_sent': False,
                    'task_tag': f"#task-{message.task.id}" if message.task else None,
                })
            
            return JsonResponse({
                'success': True,
                'messages': formatted_messages
            })
            
    except (ValueError, User.DoesNotExist) as e:
        return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid conversation ID'})


@login_required
def mark_messages_read(request):
    """Mark messages as read"""
    if request.method == 'POST':
        conversation_id = request.GET.get('conversation_id')
        
        if conversation_id:
            try:
                # Parse conversation ID to get user IDs
                parts = conversation_id.split('_')
                if len(parts) == 3 and parts[0] == 'conv':
                    user1_id = int(parts[1])
                    user2_id = int(parts[2])
                    
                    # Determine other user
                    other_user_id = user2_id if request.user.id == user1_id else user1_id
                    other_user = User.objects.get(id=other_user_id)
                    
                    # Mark messages as read
                    Message.objects.filter(
                        sender=other_user,
                        recipients=request.user,
                        is_read=False
                    ).update(is_read=True)
                    
                    return JsonResponse({'success': True})
                    
            except (ValueError, User.DoesNotExist):
                pass
        
        return JsonResponse({'success': False, 'error': 'Invalid conversation ID'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})




@login_required
def get_unread_count(request):
    """Return the unread messages count for the current user (JSON)."""
    try:
        count = Message.objects.filter(recipients=request.user, is_read=False).count()
        return JsonResponse({'success': True, 'unread_count': count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def notification_counts(request):
    """Return JSON with unread notification and message counts for header polling."""
    try:
        notifications = Notification.objects.filter(user=request.user, is_read=False).count()
        messages = Message.objects.filter(recipients=request.user, is_read=False).count()
        return JsonResponse({'success': True, 'notifications': notifications, 'messages': messages})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

