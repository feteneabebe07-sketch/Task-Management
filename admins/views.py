# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta
import json
from employee.views import (
    calculate_weekly_hours, calculate_sprint_hours, calculate_monthly_hours,
    get_upcoming_deadlines )
from core.models import (
    User, Department, EmployeeProfile, Project, Task,
    Sprint, UserActivity, Message, Notification,StandupUpdate
)
from django.db.models import Count, Q, Sum
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
def logout_view(request):
    """Logout view for all users"""
    if request.user.is_authenticated:
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action='Logged out',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        logout(request)
    return redirect('login')
def employee_login_view(request):
    """Login view for all users (Admin, PM, Developer)"""
    if request.user.is_authenticated:
        # Redirect based on role
        if request.user.role == 'admin' or request.user.is_staff:
            return redirect('admins:dashboard')
        elif request.user.role == 'pm':
            return redirect('pm_dashboard')
        else:
            return redirect('admins:dashboards')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                
                # Log activity
                UserActivity.objects.create(
                    user=user,
                    action='Logged in',
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
                # Get next URL from request or use default
                next_url = request.GET.get('next') or request.POST.get('next')
                
                if next_url:
                    return redirect(next_url)
                
                # Redirect based on role
                if user.role == 'admin' or user.is_staff:
                    return redirect('admins:dashboard')
                elif user.role == 'pm':
                    return redirect('pm_dashboard')
                else:
                    return redirect('admins:dashboards')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()

    
    return render(request, 'accounts/login.html', {'form': form})
@login_required
def pm_dashboard_view(request):
    """Forward legacy admin PM dashboard route to the PM app dashboard."""
    if request.user.role != 'pm' and not request.user.is_staff:
        return redirect('employee:dashboard')
    return redirect('pm_dashboard')
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
    
    return render(request, 'employee/dashboard.html', context)
@login_required
def employee_dashboard_view(request):
    """Employee Dashboard - to be implemented"""
    if request.user.role == 'admin' or request.user.is_staff:
        return redirect('admins:dashboard')
    elif request.user.role == 'pm':
        return redirect('pm_dashboard')
    return render(request, 'admins/employee_dashboard.html', {})
@login_required
@staff_member_required
def activity_log_view(request):
    """Render activity log page"""
    activities = UserActivity.objects.select_related('user').all()
    
    # Pagination
    paginator = Paginator(activities, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'activities': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'activity_log.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_task(request):
    """API endpoint to create task"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['title', 'project_id', 'due_date']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'{field.replace("_", " ").title()} is required'}, status=400)
        
        # Get project
        project = Project.objects.get(id=data['project_id'])
        
        # Create task
        task = Task.objects.create(
            title=data['title'],
            description=data.get('description', ''),
            project=project,
            assigned_to_id=data.get('assigned_to'),
            task_type=data.get('task_type', 'feature'),
            priority=data.get('priority', 'medium'),
            status='todo',
            estimated_hours=data.get('estimated_hours', 2),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date(),
            created_by=request.user
        )
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Created task: {task.title}',
            description=f'Task created in project: {project.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Send notification if assigned
        if task.assigned_to:
            Notification.objects.create(
                user=task.assigned_to.user,
                notification_type='task_assigned',
                title='New Task Assigned',
                message=f'You have been assigned a new task: {task.title}',
                related_id=task.id,
                related_type='task'
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Task created successfully',
            'task_id': task.id,
            'reload': True
        })
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_send_announcement(request):
    """API endpoint to send announcement"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if not data.get('subject') or not data.get('content'):
            return JsonResponse({'error': 'Subject and content are required'}, status=400)
        
        # Get recipients
        recipients = []
        recipient_data = data.get('recipients', '').split(',')
        
        for recipient in recipient_data:
            if recipient == 'all':
                recipients.extend(User.objects.filter(is_active=True))
            elif recipient == 'pms':
                recipients.extend(User.objects.filter(role='pm', is_active=True))
            elif recipient.startswith('department:'):
                dept_id = recipient.split(':')[1]
                employees = EmployeeProfile.objects.filter(
                    department_id=dept_id, 
                    status='active'
                ).select_related('user')
                recipients.extend([emp.user for emp in employees])
        
        # Remove duplicates
        recipients = list(set(recipients))
        
        # Create message
        message = Message.objects.create(
            sender=request.user,
            message_type='announcement',
            subject=data['subject'],
            content=data['content'],
            is_read=False
        )
        
        # Add recipients
        message.recipients.set(recipients)
        
        # Create notifications for recipients
        notifications = []
        for recipient in recipients:
            notifications.append(
                Notification(
                    user=recipient,
                    notification_type='message',
                    title=f'New Announcement: {data["subject"]}',
                    message=data['content'][:100] + '...',
                    related_id=message.id,
                    related_type='message'
                )
            )
        
        Notification.objects.bulk_create(notifications)
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Sent announcement: {data["subject"]}',
            description=f'To {len(recipients)} recipients',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Announcement sent to {len(recipients)} recipients',
            'recipient_count': len(recipients)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_stats_details(request, type):
    """API endpoint to get detailed statistics"""
    try:
        if type == 'projects':
            # Project statistics
            by_status = Project.objects.values('status').annotate(
                count=Count('id')
            ).order_by('-count')
            
            by_department = Project.objects.values(
                'department__name'
            ).annotate(
                count=Count('id')
            ).order_by('-count')
            
            return JsonResponse({
                'by_status': list(by_status),
                'by_department': list(by_department)
            })
            
        elif type == 'employees':
            # Employee statistics
            by_role = User.objects.values('role').annotate(
                count=Count('id')
            ).order_by('-count')
            
            by_department = EmployeeProfile.objects.values(
                'department__name'
            ).annotate(
                count=Count('id')
            ).order_by('-count')
            
            return JsonResponse({
                'by_role': list(by_role),
                'by_department': list(by_department)
            })
            
        elif type == 'tasks':
            # Task statistics
            by_status = Task.objects.values('status').annotate(
                count=Count('id')
            ).order_by('-count')
            
            by_priority = Task.objects.values('priority').annotate(
                count=Count('id')
            ).order_by('-count')
            
            return JsonResponse({
                'by_status': list(by_status),
                'by_priority': list(by_priority)
            })
            
        else:
            return JsonResponse({'error': 'Invalid statistics type'}, status=400)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@login_required
@staff_member_required
def dashboard_view(request):
    """Render the admin dashboard"""
    # Get stats
    total_projects = Project.objects.count()
    total_employees = EmployeeProfile.objects.filter(status='active').count()
    active_pms = User.objects.filter(role='pm', is_active=True).count()
    pending_tasks = Task.objects.filter(status__in=['todo', 'in_progress']).count()
    
    # Get this month's stats
    today = timezone.now()
    first_day_of_month = today.replace(day=1)
    
    new_projects_this_month = Project.objects.filter(
        created_at__gte=first_day_of_month
    ).count()
    
    new_employees_this_month = EmployeeProfile.objects.filter(
        hire_date__gte=first_day_of_month
    ).count()
    
    overdue_tasks = Task.objects.filter(
        due_date__lt=today,
        status__in=['todo', 'in_progress']
    ).count()
    
    # Get active projects with progress
    active_projects = Project.objects.filter(status='active').order_by('-due_date')[:5]
    
    # Add color classes for progress bars
    color_classes = ['dark-teal', 'dark-cyan', 'golden-orange', 'rusty-spice', 'oxidized-iron']
    for i, project in enumerate(active_projects):
        # Compute progress based on tasks (completed / total)
        total_tasks = Task.objects.filter(project=project).count()
        completed_tasks = Task.objects.filter(project=project, status='done').count()
        try:
            project.progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        except Exception:
            project.progress = getattr(project, 'progress', 0) or 0

        project.color_class = color_classes[i % len(color_classes)]
    
    # Get recent activities
    recent_activities = UserActivity.objects.select_related('user').order_by('-created_at')[:10]
    
    # Add color classes for activity dots
    activity_colors = {
        'created': 'dark-teal',
        'updated': 'dark-cyan',
        'completed': 'golden-orange',
        'assigned': 'pearl-aqua'
    }
    
    for activity in recent_activities:
        for key, color in activity_colors.items():
            if key in activity.action.lower():
                activity.color_class = color
                break
        else:
            activity.color_class = 'gray-500'
    
    # Context data for modals
    managers = User.objects.filter(
        role__in=['admin', 'pm'], 
        is_active=True
    )
    
    departments = Department.objects.filter(status='active')
    
    project_managers = User.objects.filter(
        role='pm', 
        is_active=True
    ).select_related('employee_profile')
    
    unassigned_projects = Project.objects.filter(
        status__in=['draft', 'active'],
        project_manager__isnull=True
    )
    
    employees = EmployeeProfile.objects.filter(
        status='active'
    ).select_related('user')
    
    context = {
        'total_projects': total_projects,
        'total_employees': total_employees,
        'active_pms': active_pms,
        'pending_tasks': pending_tasks,
        'new_projects_this_month': new_projects_this_month,
        'new_employees_this_month': new_employees_this_month,
        'overdue_tasks': overdue_tasks,
        'active_projects': active_projects,
        'recent_activities': recent_activities,
        'managers': managers,
        'departments': departments,
        'project_managers': project_managers,
        'unassigned_projects': unassigned_projects,
        'employees': employees,
    }
    
    return render(request, 'admins/dashboard.html', context)


@login_required
@staff_member_required
def departments_view(request):
    """Render departments page"""
    departments = Department.objects.select_related('manager').prefetch_related('employees').all()
    
    # Get stats for each department
    for dept in departments:
        dept.employee_count = dept.employees.count()
        dept.project_count = dept.projects.count()
        dept.active_project_count = dept.projects.filter(status='active').count()
    
    # Get managers for dropdown
    managers = User.objects.filter(
        role__in=['admin', 'pm'], 
        is_active=True
    )
    active_projects = Project.objects.filter(status='active').count()
    total_employees = sum(dept.employee_count for dept in departments)
    total_depts = departments.count()
    avg_team_size = total_employees / total_depts if total_depts > 0 else 0
    context = {
        'departments': departments,
        'managers': managers,
        'active_projects': active_projects,
        'total_employees': total_employees,
        'avg_team_size': round(avg_team_size, 1),
    }
    return render(request, 'admins/departments.html', context)


@login_required
@staff_member_required
def employees_view(request):
    """Render employees page"""
    employees = EmployeeProfile.objects.select_related(
        'user', 'department'
    ).filter(status='active')
    employees_count = employees.count()
    
    # Get departments for dropdown
    departments = Department.objects.filter(status='active')
    employees_active_rate = (employees_count / EmployeeProfile.objects.count() * 100) if EmployeeProfile.objects.count() > 0 else 0
    employees_on_leave = EmployeeProfile.objects.filter(
        leave_requests__status='approved',
        leave_requests__start_date__lte=timezone.now().date(),
        leave_requests__end_date__gte=timezone.now().date()
    ).distinct().count()
    employees_return_soon = EmployeeProfile.objects.filter(
        leave_requests__status='approved',
        leave_requests__end_date__gt=timezone.now().date(),
        leave_requests__end_date__lte=(timezone.now() + timedelta(days=7)).date()
    ).distinct().count()
    context = {
        'employees': employees,
        'departments': departments,
        'employees_count': employees_count,
        'employees_active_rate': round(employees_active_rate, 1),
        'employees_on_leave': employees_on_leave,
        'employees_return_soon': employees_return_soon,
    }
    return render(request, 'admins/employees.html', context)


@login_required
@staff_member_required
def projects_view(request):
    """Render projects page"""
    # Annotate projects with task counts to compute accurate progress
    projects = Project.objects.select_related(
        'department', 'project_manager'
    ).prefetch_related('members').annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__status='done'))
    ).all()
    
    # Get departments and project managers for dropdowns
    departments = Department.objects.filter(status='active')
    project_managers = User.objects.filter(
        role='pm', 
        is_active=True
    ).select_related('employee_profile')
    
    # Add current time for overdue calculation
    from django.utils import timezone
    now = timezone.now()
    active_project_count = projects.filter(status='active').count()
    completed_projects_count = projects.filter(status='completed').count()
    # Compute progress percent for each project using annotated counts
    for project in projects:
        total = getattr(project, 'total_tasks', 0) or 0
        completed = getattr(project, 'completed_tasks', 0) or 0
        try:
            project.progress = int((completed / total) * 100) if total > 0 else 0
        except Exception:
            project.progress = getattr(project, 'progress', 0) or 0
    context = {
        'projects': projects,
        'departments': departments,
        'project_managers': project_managers,
        'now': now,
        'active_projects_count': active_project_count,
        'completed_projects_count': completed_projects_count,
    }
    return render(request, 'admins/projects.html', context)




# API Views
@csrf_exempt
@require_http_methods(["POST"])
def api_create_department(request):
    """API endpoint to create department"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if not data.get('name'):
            return JsonResponse({'error': 'Department name is required'}, status=400)
        
        # Create department
        department = Department.objects.create(
            name=data['name'],
            description=data.get('description', ''),
            manager_id=data.get('manager'),
            status='active'
        )
        
        # Create department stats
        from core.models import DepartmentStats
        DepartmentStats.objects.create(department=department)
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Created department: {department.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Department created successfully',
            'department_id': department.id,
            'reload': True
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_employee(request):
    """API endpoint to create employee"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['full_name', 'email', 'department', 'role', 'join_date']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'{field.replace("_", " ").title()} is required'}, status=400)
        
        # Create user
        user = User.objects.create(
            username=data['email'],
            email=data['email'],
            first_name=data['full_name'].split()[0] if ' ' in data['full_name'] else data['full_name'],
            last_name=' '.join(data['full_name'].split()[1:]) if ' ' in data['full_name'] else '',
            role=data['role'],
            phone=data.get('phone'),
            is_active=True
        )
        
        # Set password (default password)
        user.set_password('password123')
        user.save()
        
        # Create employee profile
        employee = EmployeeProfile.objects.create(
            user=user,
            employee_id=f"EMP{user.id:04d}",
            department_id=data['department'],
            job_position=data['position'],
            hire_date=datetime.strptime(data['join_date'], '%Y-%m-%d').date(),
            skills=data.get('skills', ''),
            phone=data.get('phone'),
            status='active'
        )
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Registered employee: {employee.get_full_name()}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Employee registered successfully',
            'employee_id': employee.id,
            'reload': True
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_project(request):
    """API endpoint to create project"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['title', 'description', 'department', 'project_type', 'start_date', 'end_date']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'{field.replace("_", " ").title()} is required'}, status=400)
        
        # Create project
        # Prepare fields, allowing optional values from the frontend
        status = data.get('status', 'draft')
        progress = 0
        try:
            progress = int(data.get('progress', 0) or 0)
        except (ValueError, TypeError):
            progress = 0

        project_kwargs = {
            'name': data['title'],
            'description': data['description'],
            'department_id': data['department'],
            'project_type': data['project_type'],
            'status': status,
            'progress': progress,
            'start_date': datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            'due_date': datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            'created_by': request.user,
        }

        # Optional numeric fields
        if data.get('budget') not in (None, '', 'null'):
            try:
                project_kwargs['budget'] = data.get('budget')
            except Exception:
                pass

        # Optional project manager assignment at creation
        pm_id = data.get('project_manager') or data.get('project_manager_id')
        if pm_id:
            try:
                project_kwargs['project_manager_id'] = int(pm_id)
            except (ValueError, TypeError):
                # ignore invalid id
                pass

        project = Project.objects.create(**project_kwargs)
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Created project: {project.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Project created successfully',
            'project_id': project.id,
            'reload': True
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_assign_pm(request):
    """API endpoint to assign project manager"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        if not data.get('project_id'):
            return JsonResponse({'error': 'Project is required'}, status=400)
        if not data.get('pm_id'):
            return JsonResponse({'error': 'Project manager is required'}, status=400)
        
        # Get project and PM
        project = Project.objects.get(id=data['project_id'])
        pm = User.objects.get(id=data['pm_id'])
        
        # Assign PM
        project.project_manager = pm
        project.save()
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Assigned {pm.get_full_name()} as PM for {project.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Project manager assigned successfully',
            'reload': True
        })
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)





@require_http_methods(["GET"])
def api_dashboard_stats(request):
    """API endpoint to get dashboard stats"""
    try:
        total_projects = Project.objects.count()
        total_employees = EmployeeProfile.objects.filter(status='active').count()
        active_pms = User.objects.filter(role='pm', is_active=True).count()
        pending_tasks = Task.objects.filter(status__in=['todo', 'in_progress']).count()
        
        today = timezone.now()
        first_day_of_month = today.replace(day=1)
        
        new_projects_this_month = Project.objects.filter(
            created_at__gte=first_day_of_month
        ).count()
        
        new_employees_this_month = EmployeeProfile.objects.filter(
            hire_date__gte=first_day_of_month
        ).count()
        
        overdue_tasks = Task.objects.filter(
            due_date__lt=today,
            status__in=['todo', 'in_progress']
        ).count()
        
        return JsonResponse({
            'total_projects': total_projects,
            'total_employees': total_employees,
            'active_pms': active_pms,
            'pending_tasks': pending_tasks,
            'new_projects_this_month': new_projects_this_month,
            'new_employees_this_month': new_employees_this_month,
            'overdue_tasks': overdue_tasks,
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_notification_count(request):
    """API endpoint to get unread notification count"""
    try:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return JsonResponse({'count': count})
    except Exception as e:
        return JsonResponse({'count': 0})



    


    #departments

 # Add these imports at the top if not already present
from django.forms.models import model_to_dict
from django.core import serializers

# Add these functions to your views.py
@csrf_exempt
@require_http_methods(["GET"])
def api_get_department(request, department_id):
    """API endpoint to get department details"""
    try:
        department = Department.objects.select_related('manager').get(id=department_id)
        
        # Get department stats
        employee_count = department.employees.count()
        project_count = department.projects.count()
        active_project_count = department.projects.filter(status='active').count()
        
        department_data = {
            'id': department.id,
            'name': department.name,
            'description': department.description,
            'status': department.status,
            'created_at': department.created_at.strftime('%Y-%m-%d %H:%M:%S') if department.created_at else None,
            'updated_at': department.updated_at.strftime('%Y-%m-%d %H:%M:%S') if department.updated_at else None,
            'employee_count': employee_count,
            'project_count': project_count,
            'active_project_count': active_project_count,
        }
        
        if department.manager:
            department_data['manager'] = {
                'id': department.manager.id,
                'full_name': department.manager.get_full_name(),
                'first_name': department.manager.first_name,
                'last_name': department.manager.last_name,
                'email': department.manager.email,
                'username': department.manager.username,
            }
        
        return JsonResponse(department_data)
        
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_department(request, department_id):
    """API endpoint to update department"""
    try:
        department = Department.objects.get(id=department_id)
        data = json.loads(request.body)
        
        # Update fields
        if 'name' in data:
            department.name = data['name']
        if 'description' in data:
            department.description = data['description']
        if 'manager' in data:
            if data['manager']:
                try:
                    manager = User.objects.get(id=data['manager'])
                    department.manager = manager
                except User.DoesNotExist:
                    return JsonResponse({'error': 'Manager not found'}, status=404)
            else:
                department.manager = None
        if 'status' in data:
            department.status = data['status']
        
        department.save()
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Updated department: {department.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Department updated successfully',
            'department_id': department.id,
            'reload': True
        })
        
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
#employees

@csrf_exempt
@require_http_methods(["GET"])
def api_get_employee(request, employee_id):
    """API endpoint to get employee details"""
    try:
        employee = EmployeeProfile.objects.select_related(
            'user', 'department'
        ).get(id=employee_id)
        
        employee_data = {
            'id': employee.id,
            'full_name': employee.user.get_full_name(),
            'email': employee.user.email,
            'phone': employee.phone,
            'department_id': employee.department.id if employee.department else None,
            'department_name': employee.department.name if employee.department else None,
            'role': employee.user.role,
            'job_position': employee.job_position,
            'employee_id': employee.employee_id,
            'salary': str(employee.salary) if employee.salary else None,
            'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else None,
            'skills': employee.skills,
            'status': employee.status,
            'created_at': employee.created_at.strftime('%Y-%m-%d %H:%M:%S') if employee.created_at else None,
        }

        # Include current projects the employee is a member of
        try:
            proj_members = employee.project_memberships.select_related('project').filter(is_active=True)
            current_projects = []
            for pm in proj_members:
                p = pm.project
                current_projects.append({
                    'id': p.id,
                    'name': p.name,
                    'status': p.status,
                    'progress': p.progress,
                    'due_date': p.due_date.strftime('%Y-%m-%d') if p.due_date else None,
                    'role': pm.role,
                })
            employee_data['current_projects'] = current_projects
        except Exception:
            employee_data['current_projects'] = []
        
        return JsonResponse(employee_data)
        
    except EmployeeProfile.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_employee(request, employee_id):
    """API endpoint to update employee"""
    try:
        employee = EmployeeProfile.objects.select_related('user').get(id=employee_id)
        data = json.loads(request.body)
        
        # Update user fields
        if 'full_name' in data:
            name_parts = data['full_name'].split(' ', 1)
            employee.user.first_name = name_parts[0]
            employee.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            employee.user.save()
        
        if 'email' in data:
            employee.user.email = data['email']
            employee.user.username = data['email']  # Assuming username is email
            employee.user.save()
        
        if 'role' in data:
            employee.user.role = data['role']
            employee.user.save()
        
        # Update employee profile fields
        if 'phone' in data:
            employee.phone = data['phone']
        
        if 'department' in data:
            try:
                department = Department.objects.get(id=data['department'])
                employee.department = department
            except Department.DoesNotExist:
                return JsonResponse({'error': 'Department not found'}, status=404)
        
        if 'position' in data:
            employee.job_position = data['position']
        
        if 'salary' in data and data['salary']:
            try:
                employee.salary = float(data['salary'])
            except ValueError:
                pass
        
        if 'join_date' in data and data['join_date']:
            try:
                employee.hire_date = datetime.strptime(data['join_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if 'skills' in data:
            employee.skills = data['skills']
        
        if 'status' in data:
            employee.status = data['status']
        
        employee.save()
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Updated employee: {employee.user.get_full_name()}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Employee updated successfully',
            'employee_id': employee.id,
            'reload': True
        })
        
    except EmployeeProfile.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
#projects
@csrf_exempt
@require_http_methods(["GET"])
def api_get_project(request, project_id):
    """API endpoint to get project details"""
    try:
        project = Project.objects.select_related(
            'department', 'project_manager'
        ).get(id=project_id)
        
        # Build project payload including team members for the admin UI
        project_data = {
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'department_id': project.department.id if project.department else None,
            'department': {
                'id': project.department.id if project.department else None,
                'name': project.department.name if project.department else None,
            } if project.department else None,
            'project_type': project.project_type,
            'status': project.status,
            'progress': project.progress,
            'budget': str(project.budget) if project.budget else None,
            'start_date': project.start_date.strftime('%Y-%m-%d') if project.start_date else None,
            'end_date': project.due_date.strftime('%Y-%m-%d') if project.due_date else None,
            'project_manager_id': project.project_manager.id if project.project_manager else None,
            'project_manager': {
                'id': project.project_manager.id if project.project_manager else None,
                'get_full_name': project.project_manager.get_full_name() if project.project_manager else None,
                'first_name': project.project_manager.first_name if project.project_manager else None,
                'last_name': project.project_manager.last_name if project.project_manager else None,
                'username': project.project_manager.username if project.project_manager else None,
            } if project.project_manager else None,
            'created_at': project.created_at.strftime('%Y-%m-%d %H:%M:%S') if project.created_at else None,
            'updated_at': project.updated_at.strftime('%Y-%m-%d %H:%M:%S') if project.updated_at else None,
        }

        # Include active team members inline to simplify the frontend logic
        try:
            members_qs = project.members.select_related('employee__user').filter(is_active=True)
            team_members = []
            for m in members_qs:
                emp = m.employee
                user = emp.user
                team_members.append({
                    'id': emp.id,
                    'employee_id': getattr(emp, 'employee_id', None),
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'get_full_name': user.get_full_name(),
                    'username': user.username,
                    'email': user.email,
                    'position': getattr(emp, 'job_position', None),
                    'role': m.role,
                    'joined_at': m.joined_at.strftime('%Y-%m-%d %H:%M:%S') if m.joined_at else None,
                })
            project_data['team_members'] = team_members
        except Exception:
            project_data['team_members'] = []
        
        return JsonResponse(project_data)
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_get_project_team(request, project_id):
    """API endpoint to return team members for a project"""
    try:
        project = Project.objects.get(id=project_id)
        # Get active members
        members_qs = project.members.select_related('employee__user').filter(is_active=True)
        members = []
        for m in members_qs:
            emp = m.employee
            members.append({
                'id': emp.id,
                'employee_id': emp.employee_id,
                'first_name': emp.user.first_name,
                'last_name': emp.user.last_name,
                'full_name': emp.user.get_full_name(),
                'username': emp.user.username,
                'email': emp.user.email,
                'position': emp.job_position,
                'role': m.role,
                'joined_at': m.joined_at.strftime('%Y-%m-%d %H:%M:%S') if m.joined_at else None,
            })

        return JsonResponse(members, safe=False)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_project(request, project_id):
    """API endpoint to update project"""
    try:
        project = Project.objects.get(id=project_id)
        data = json.loads(request.body)
        
        # Update fields
        if 'title' in data or 'name' in data:
            project.name = data.get('title') or data.get('name')
        if 'description' in data:
            project.description = data['description']
        if 'department' in data:
            try:
                department = Department.objects.get(id=data['department'])
                project.department = department
            except Department.DoesNotExist:
                return JsonResponse({'error': 'Department not found'}, status=404)
        if 'project_type' in data:
            project.project_type = data['project_type']
        if 'status' in data:
            project.status = data['status']
        if 'progress' in data:
            try:
                project.progress = int(data['progress'])
            except (ValueError, TypeError):
                pass
        if 'budget' in data and data['budget']:
            try:
                project.budget = float(data['budget'])
            except ValueError:
                pass
        if 'start_date' in data and data['start_date']:
            try:
                project.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        if 'end_date' in data and data['end_date']:
            try:
                project.due_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        if 'project_manager' in data:
            if data['project_manager']:
                try:
                    manager = User.objects.get(id=data['project_manager'])
                    project.project_manager = manager
                except User.DoesNotExist:
                    return JsonResponse({'error': 'Project manager not found'}, status=404)
            else:
                project.project_manager = None
        
        project.save()
        
        # Log activity
        UserActivity.objects.create(
            user=request.user,
            action=f'Updated project: {project.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Project updated successfully',
            'project_id': project.id,
            'reload': True
        })
        
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

import csv
from django.http import HttpResponse
from io import StringIO



@login_required
@staff_member_required
def export_projects_csv(request):
    """Export projects as CSV"""
    # Create a response object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="projects_export.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'ID', 'Name', 'Description', 'Department', 'Project Type',
        'Status', 'Progress (%)', 'Budget', 'Start Date', 'Due Date',
        'Project Manager', 'Created At'
    ])
    
    # Get all projects with related data
    projects = Project.objects.select_related(
        'department', 'project_manager'
    ).all()
    
    # Write data rows
    for project in projects:
        writer.writerow([
            project.id,
            project.name,
            project.description or '',
            project.department.name if project.department else '',
            project.project_type,
            project.status,
            project.progress,
            project.budget or '',
            project.start_date.strftime('%Y-%m-%d') if project.start_date else '',
            project.due_date.strftime('%Y-%m-%d') if project.due_date else '',
            project.project_manager.get_full_name() if project.project_manager else '',
            project.created_at.strftime('%Y-%m-%d %H:%M:%S') if project.created_at else ''
        ])
    
    # Log activity
    UserActivity.objects.create(
        user=request.user,
        action='Exported projects report',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return response

@login_required
@staff_member_required
def export_employees_csv(request):
    """Export employees as CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employees_export.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Employee ID', 'Full Name', 'Email', 'Phone', 'Department',
        'Job Position', 'Role', 'Hire Date', 'Salary', 'Skills',
        'Status', 'Created At'
    ])
    
    # Get all active employees
    employees = EmployeeProfile.objects.select_related(
        'user', 'department'
    ).filter(status='active')
    
    for emp in employees:
        writer.writerow([
            emp.employee_id,
            emp.user.get_full_name(),
            emp.user.email,
            emp.phone or '',
            emp.department.name if emp.department else '',
            emp.job_position,
            emp.user.role,
            emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
            emp.salary or '',
            emp.skills or '',
            emp.status,
            emp.created_at.strftime('%Y-%m-%d %H:%M:%S') if emp.created_at else ''
        ])
    
    # Log activity
    UserActivity.objects.create(
        user=request.user,
        action='Exported employees report',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return response

@login_required
@staff_member_required
def export_tasks_csv(request):
    """Export tasks as CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tasks_export.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'ID', 'Title', 'Description', 'Project', 'Assigned To',
        'Task Type', 'Priority', 'Status', 'Estimated Hours',
        'Actual Hours', 'Due Date', 'Created At', 'Completed At'
    ])
    
    # Get all tasks
    tasks = Task.objects.select_related(
        'project', 'assigned_to__user'
    ).all()
    
    for task in tasks:
        writer.writerow([
            task.id,
            task.title,
            task.description or '',
            task.project.name if task.project else '',
            task.assigned_to.user.get_full_name() if task.assigned_to else '',
            task.task_type,
            task.priority,
            task.status,
            task.estimated_hours or 0,
            task.actual_hours or 0,
            task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else '',
            task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else ''
        ])
    
    # Log activity
    UserActivity.objects.create(
        user=request.user,
        action='Exported tasks report',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return response

@login_required
@staff_member_required
def export_departments_csv(request):
    """Export departments as CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="departments_export.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'ID', 'Name', 'Description', 'Manager', 'Employee Count',
        'Project Count', 'Status', 'Created At'
    ])
    
    # Get all departments
    departments = Department.objects.select_related('manager').all()
    
    for dept in departments:
        writer.writerow([
            dept.id,
            dept.name,
            dept.description or '',
            dept.manager.get_full_name() if dept.manager else '',
            dept.employees.count(),
            dept.projects.count(),
            dept.status,
            dept.created_at.strftime('%Y-%m-%d %H:%M:%S') if dept.created_at else ''
        ])
    
    # Log activity
    UserActivity.objects.create(
        user=request.user,
        action='Exported departments report',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return response

@login_required
@staff_member_required
def export_recent_activity_csv(request):
    """Export recent activity as CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="activity_log_export.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'ID', 'User', 'Action', 'Details', 'IP Address', 'Timestamp'
    ])
    
    # Get recent activities (last 500 records)
    activities = UserActivity.objects.select_related('user').all()[:500]
    
    for activity in activities:
        writer.writerow([
            activity.id,
            activity.user.get_full_name() if activity.user else '',
            activity.action,
            activity.details or '',
            activity.ip_address or '',
            activity.created_at.strftime('%Y-%m-%d %H:%M:%S') if activity.created_at else ''
        ])
    
    # Log activity
    UserActivity.objects.create(
        user=request.user,
        action='Exported activity log',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return response

