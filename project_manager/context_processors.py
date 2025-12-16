# context_processors.py
from core.models import Project, ProjectMember

def pm_context(request):
    """Add PM-specific context to all templates"""
    context = {}
    
    if request.user.is_authenticated and (request.user.role == 'pm' or request.user.role == 'admin'):
        # Get all projects managed by this PM
        managed_projects = Project.objects.filter(
            project_manager=request.user
        ).select_related('department').order_by('name')
        
        context['managed_projects'] = managed_projects
        
        # For project selection in modals, we need active project context
        # This can be overridden in individual views
        if hasattr(request, 'active_project'):
            context['active_project'] = request.active_project
            
            # Get active project members for task assignment
            active_project_members = ProjectMember.objects.filter(
                project=request.active_project,
                is_active=True
            ).select_related('employee__user')
            
            member_data = []
            for member in active_project_members:
                user = member.employee.user
                initials = f"{user.first_name[0]}{user.last_name[0]}".upper()
                
                member_data.append({
                    'member': member,
                    'user_full_name': user.get_full_name(),
                    'initials': initials,
                })
            
            context['member_data'] = member_data
    
    return context