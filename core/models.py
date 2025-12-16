from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ==================== USERS MODELS ====================
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('pm', 'Project Manager'),
        ('developer', 'Developer'),
        ('designer', 'Designer'),
        ('qa', 'QA Tester'),
        ('hr', 'HR Manager'),
        ('sales', 'Sales Executive'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='developer')
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'users'
        
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


# ==================== DEPARTMENT MODELS ====================
class Department(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, 
                              null=True, blank=True, related_name='managed_departments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return self.name
    
    def get_employee_count(self):
        return self.employees.count()
    
    def get_active_project_count(self):
        return self.projects.filter(status='active').count()


class DepartmentStats(models.Model):
    department = models.OneToOneField(Department, on_delete=models.CASCADE, related_name='stats')
    total_employees = models.IntegerField(default=0)
    active_projects = models.IntegerField(default=0)
    completed_projects = models.IntegerField(default=0)
    avg_team_size = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


# ==================== EMPLOYEE MODELS ====================
class EmployeeProfile(models.Model):
    EMPLOYEE_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
        ('terminated', 'Terminated'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, 
                                 null=True, related_name='employees')
    job_position = models.CharField(max_length=100, blank=True, null=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hire_date = models.DateField()
    skills = models.TextField(blank=True)  # Comma-separated skills
    status = models.CharField(max_length=20, choices=EMPLOYEE_STATUS, default='active')
    phone = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['user__last_name', 'user__first_name']
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.employee_id}"
    
    def get_full_name(self):
        return self.user.get_full_name()
    
    def get_email(self):
        return self.user.email
    
    def get_active_task_count(self):
        return self.assigned_tasks.filter(status__in=['todo', 'in_progress']).count()


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('vacation', 'Vacation'),
        ('sick', 'Sick Leave'),
        ('personal', 'Personal Leave'),
        ('maternity', 'Maternity Leave'),
        ('paternity', 'Paternity Leave'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


# ==================== PROJECT MODELS ====================
class Project(models.Model):
    PROJECT_TYPE_CHOICES = [
        ('web', 'Web Application'),
        ('mobile', 'Mobile Application'),
        ('research', 'Research Project'),
        ('internal', 'Internal System'),
        ('client', 'Client Project'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='projects')
    project_manager = models.ForeignKey(User, on_delete=models.SET_NULL, 
                                       null=True, related_name='managed_projects')
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    progress = models.IntegerField(default=0)  # Percentage
    start_date = models.DateField()
    due_date = models.DateField()
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, 
                                 related_name='created_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return self.name
    
    def days_remaining(self):
        today = timezone.now().date()
        if today > self.due_date:
            return 0
        return (self.due_date - today).days
    
    def is_delayed(self):
        today = timezone.now().date()
        return today > self.due_date and self.status == 'active'


class ProjectMember(models.Model):
    ROLE_CHOICES = [
        ('pm', 'Project Manager'),
        ('dev', 'Developer'),
        ('designer', 'Designer'),
        ('qa', 'QA Tester'),
        ('analyst', 'Business Analyst'),
        ('other', 'Other'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, 
                               related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['project', 'employee']
        ordering = ['-joined_at']


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='project_files/')
    name = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']


# ==================== SPRINT MODELS ====================
class Sprint(models.Model):
    SPRINT_STATUS = [
        ('planned', 'Planned'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sprints')
    name = models.CharField(max_length=100)
    goal = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=SPRINT_STATUS, default='planned')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.name} - {self.project.name}"
    
    def total_points(self):
        return sum(task.estimated_hours for task in self.tasks.all())
    
    def completed_points(self):
        return sum(task.estimated_hours for task in self.tasks.filter(status='done'))
    
    def progress_percentage(self):
        total = self.total_points()
        if total == 0:
            return 0
        return int((self.completed_points() / total) * 100)
    
    def days_remaining(self):
        today = timezone.now().date()
        if today > self.end_date:
            return 0
        return (self.end_date - today).days


class SprintReport(models.Model):
    sprint = models.OneToOneField(Sprint, on_delete=models.CASCADE, related_name='report')
    total_tasks = models.IntegerField(default=0)
    completed_tasks = models.IntegerField(default=0)
    total_estimated_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_actual_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    velocity = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    blockers = models.TextField(blank=True)
    lessons_learned = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


# ==================== TASK MODELS ====================
class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('review', 'In Review'),
        ('done', 'Done'),
        ('blocked', 'Blocked'),
    ]
    
    TASK_TYPE_CHOICES = [
        ('bug', 'Bug'),
        ('feature', 'Feature'),
        ('improvement', 'Improvement'),
        ('research', 'Research'),
        ('documentation', 'Documentation'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    sprint = models.ForeignKey(Sprint, on_delete=models.SET_NULL, 
                             null=True, blank=True, related_name='tasks')
    assigned_to = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='assigned_tasks')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='feature')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    progress = models.IntegerField(default=0)  # Percentage
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField()
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, 
                                 related_name='created_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    def is_overdue(self):
        today = timezone.now().date()
        return self.status != 'done' and today > self.due_date


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']


class TaskDependency(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='dependencies')
    depends_on = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='dependents')
    
    class Meta:
        unique_together = ['task', 'depends_on']
        ordering = ['task']


class TimeLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, 
                               related_name='time_logs')
    date = models.DateField()
    hours = models.DecimalField(max_digits=4, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']


class TaskFile(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='task_files/')
    name = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']


# ==================== COMMUNICATION MODELS ====================
class Message(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ('direct', 'Direct Message'),
        ('group', 'Group Chat'),
        ('task', 'Task Discussion'),
        ('project', 'Project Discussion'),
        ('announcement', 'Announcement'),
    ]
    
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipients = models.ManyToManyField(User, related_name='received_messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES)
    subject = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, 
                           related_name='messages')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, 
                              null=True, blank=True, related_name='messages')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Message from {self.sender}"
    @property
    def sender_initials(self):
        """Get sender's initials"""
        if self.sender.get_full_name():
            names = self.sender.get_full_name().split()
            if len(names) >= 2:
                return f"{names[0][0]}{names[1][0]}".upper()
        return self.sender.username[:2].upper()
    
    @property
    def sender_color(self):
        """Return consistent color for sender"""
        colors = ['bg-dark-cyan', 'bg-golden-orange', 'bg-rusty-spice', 'bg-dark-teal']
        # Use sender ID to get consistent color
        color_index = self.sender.id % len(colors) if self.sender.id else 0
        return colors[color_index]


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    mentions = models.ManyToManyField(User, related_name='mentioned_in_comments', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('task_assigned', 'Task Assigned'),
        ('task_updated', 'Task Updated'),
        ('task_completed', 'Task Completed'),
        ('comment', 'New Comment'),
        ('message', 'New Message'),
        ('project', 'Project Update'),
        ('sprint', 'Sprint Update'),
        ('approval', 'Approval Required'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    related_id = models.IntegerField(null=True, blank=True)  # ID of related object
    related_type = models.CharField(max_length=50, blank=True)  # Model name of related object
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at', '-is_read']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]


class StandupUpdate(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, 
                               related_name='standup_updates')
    date = models.DateField()
    yesterday_work = models.TextField()
    today_plan = models.TextField()
    blockers = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['employee', 'date']