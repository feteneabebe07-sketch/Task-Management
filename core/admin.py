from django.contrib import admin
from .models import (
    User, UserActivity,
    Department, DepartmentStats,
    EmployeeProfile, LeaveRequest,
    Project, ProjectMember, ProjectFile,
    Sprint, SprintReport,
    Task, Subtask, TaskDependency, TimeLog, TaskFile,
    Message, Comment, Notification, StandupUpdate
)

# ============================================================
# ======================= USER ADMIN ==========================
# ============================================================

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'get_full_name', 'email', 'role', 'is_active', 'created_at')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    list_filter = ('role', 'is_active')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('user__username', 'description')


# ============================================================
# ===================== DEPARTMENT ADMIN ======================
# ============================================================

class DepartmentStatsInline(admin.StackedInline):
    model = DepartmentStats
    can_delete = False
    extra = 0


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'manager', 'status', 'get_employee_count', 'get_active_project_count')
    list_filter = ('status',)
    search_fields = ('name', 'manager__username')
    inlines = [DepartmentStatsInline]


@admin.register(DepartmentStats)
class DepartmentStatsAdmin(admin.ModelAdmin):
    list_display = ('department', 'total_employees', 'active_projects', 'completed_projects', 'updated_at')
    readonly_fields = ('updated_at',)


# ============================================================
# ===================== EMPLOYEE ADMIN ========================
# ============================================================

@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'get_full_name', 'department', 'job_position', 'status')
    list_filter = ('status', 'department')
    search_fields = ('employee_id', 'user__first_name', 'user__last_name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'status', 'start_date', 'end_date', 'approved_at')
    list_filter = ('leave_type', 'status')
    search_fields = ('employee__user__first_name', 'employee__employee_id')
    readonly_fields = ('created_at', 'approved_at')


# ============================================================
# ===================== PROJECT ADMIN =========================
# ============================================================

class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1


class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 1


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ('title', 'status', 'priority')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'project_manager', 'status', 'progress', 'start_date', 'due_date')
    list_filter = ('project_type', 'status', 'department')
    search_fields = ('name', 'project_manager__username')
    inlines = [ProjectMemberInline, ProjectFileInline, TaskInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('project', 'employee', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active')


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


# ============================================================
# ======================= SPRINT ADMIN ========================
# ============================================================

class TaskSubInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ('title', 'status', 'priority', 'estimated_hours')


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'status', 'start_date', 'end_date')
    list_filter = ('status',)
    search_fields = ('name', 'project__name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TaskSubInline]


@admin.register(SprintReport)
class SprintReportAdmin(admin.ModelAdmin):
    list_display = ('sprint', 'total_tasks', 'completed_tasks', 'velocity', 'created_at')
    readonly_fields = ('created_at',)


# ============================================================
# ======================== TASK ADMIN =========================
# ============================================================

class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 1


class TaskFileInline(admin.TabularInline):
    model = TaskFile
    extra = 1


class TimeLogInline(admin.TabularInline):
    model = TimeLog
    extra = 1


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'assigned_to', 'priority', 'status', 'estimated_hours', 'actual_hours')
    list_filter = ('priority', 'status', 'task_type', 'project')
    search_fields = ('title', 'description')
    inlines = [SubtaskInline, TaskFileInline, TimeLogInline]
    readonly_fields = ('created_at', 'updated_at', 'completed_at')


@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ('task', 'title', 'is_completed', 'created_at')
    list_filter = ('is_completed',)


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ('task', 'depends_on')
    search_fields = ('task__title',)


@admin.register(TimeLog)
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ('task', 'employee', 'date', 'hours')
    list_filter = ('date',)


@admin.register(TaskFile)
class TaskFileAdmin(admin.ModelAdmin):
    list_display = ('task', 'name', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


# ============================================================
# ==================== COMMUNICATION ADMIN ====================
# ============================================================

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'message_type', 'subject', 'created_at', 'is_read')
    search_fields = ('sender__username', 'subject', 'content')
    list_filter = ('message_type', 'is_read', 'created_at')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'created_at')
    search_fields = ('content', 'user__username')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'message')


@admin.register(StandupUpdate)
class StandupUpdateAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'created_at')
    list_filter = ('date',)
    search_fields = ('employee__user__first_name',)
