# views/pm_helpers.py
from django.db.models import Count, Q
from core.models import Task, ProjectMember
from django.db.models import Sum
def calculate_member_task_statuses(project, project_members):
    """Calculate task counts and status indicators for team members"""
    member_data = []
    
    for member in project_members:
        # Get task count for this member
        task_count = Task.objects.filter(
            project=project,
            assigned_to=member.employee,
            status__in=['todo', 'in_progress']
        ).count()
        
        # Get member initials
        user = member.employee.user
        initials = "PM"
        if user.first_name and user.last_name:
            initials = f"{user.first_name[0]}{user.last_name[0]}"
        elif user.username:
            initials = user.username[:2].upper()
        
        # Determine status based on task count
        if task_count == 0:
            status_class = 'bg-pearl-aqua bg-opacity-10 text-pearl-aqua'
            status_text = 'Available'
        elif task_count <= 2:
            status_class = 'bg-dark-cyan bg-opacity-10 text-dark-cyan'
            status_text = f'{task_count} task{"s" if task_count != 1 else ""}'
        else:
            status_class = 'bg-rusty-spice bg-opacity-10 text-rusty-spice'
            status_text = f'{task_count} tasks'
        
        member_data.append({
            'member': member,
            'task_count': task_count,
            'status_class': status_class,
            'status_text': status_text,
            'initials': initials,
            'color_class': get_member_color_class(len(member_data)),
            'user_full_name': user.get_full_name() or user.username,
        })
    
    return member_data

def get_member_color_class(index):
    """Get consistent color class for member avatars"""
    colors = ['bg-dark-teal', 'bg-dark-cyan', 'bg-golden-orange', 'bg-rusty-spice']
    return colors[index % len(colors)]

def calculate_sprint_progress(sprint):
    """Calculate sprint progress percentage"""
    if not sprint:
        return 0
    
    sprint_tasks = Task.objects.filter(sprint=sprint)
    total_points = sprint_tasks.aggregate(total=Sum('estimated_hours'))['total'] or 0
    completed_points = sprint_tasks.filter(status='done').aggregate(
        total=Sum('estimated_hours'))['total'] or 0
    
    if total_points > 0:
        return int((completed_points / total_points) * 100)
    return 0

def get_task_priority_class(task):
    """Get CSS class for task priority"""
    priority_classes = {
        'low': 'priority-low',
        'medium': 'priority-medium',
        'high': 'priority-high',
        'critical': 'priority-high'  # Use same as high for critical
    }
    return priority_classes.get(task.priority, 'priority-medium')

def get_task_status_border_class(task):
    """Get CSS border class for task status"""
    status_border_classes = {
        'todo': 'border-golden-orange',
        'in_progress': 'border-dark-teal',
        'review': 'border-rusty-spice',
        'done': 'border-pearl-aqua',
        'blocked': 'border-oxidized-iron',
    }
    return status_border_classes.get(task.status, 'border-gray-300')

def get_task_status_text_class(task):
    """Get CSS text color class for task status"""
    status_text_classes = {
        'todo': 'text-golden-orange',
        'in_progress': 'text-dark-teal',
        'review': 'text-rusty-spice',
        'done': 'text-pearl-aqua',
        'blocked': 'text-oxidized-iron',
    }
    return status_text_classes.get(task.status, 'text-gray-600')