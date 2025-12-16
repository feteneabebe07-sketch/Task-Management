# pm/messages_api.py
import json
import os
import redis
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone

from core.models import User, EmployeeProfile, Message, Project, ProjectMember


# =====================================================
# Redis setup (SAFE)
# =====================================================
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

try:
    redis_client = redis.from_url(
        REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
        retry_on_timeout=True,
    )
    redis_client.ping()
    REDIS_AVAILABLE = True
except Exception:
    redis_client = None
    REDIS_AVAILABLE = False


def redis_exists(key):
    if not REDIS_AVAILABLE:
        return False
    try:
        return bool(redis_client.exists(key))
    except Exception:
        return False


def redis_publish(channel, payload):
    if not REDIS_AVAILABLE:
        return
    try:
        redis_client.publish(channel, json.dumps(payload))
    except Exception:
        pass


# =====================================================
# Utils
# =====================================================
def get_user_color(user_id):
    colors = [
        "dark-teal", "dark-cyan", "golden-orange",
        "rusty-spice", "oxidized-iron", "brown-red"
    ]
    return f"bg-{colors[user_id % len(colors)]}"


# =====================================================
# APIs
# =====================================================
@login_required
@require_GET
def get_conversation_messages(request, user_id):
    """Get direct conversation messages"""
    try:
        other_user = User.objects.get(id=user_id)
        current_user = request.user

        messages = Message.objects.filter(
            Q(sender=current_user, recipients=other_user, message_type="direct") |
            Q(sender=other_user, recipients=current_user, message_type="direct")
        ).order_by("created_at")

        messages_data = []
        for msg in messages:
            is_sent = msg.sender_id == current_user.id

            if not is_sent and not msg.is_read:
                msg.is_read = True
                msg.save(update_fields=["is_read"])

            messages_data.append({
                "id": msg.id,
                "content": msg.content,
                "sender_id": msg.sender.id,
                "sender_name": msg.sender.get_full_name(),
                "initials": (
                    f"{msg.sender.first_name[:1]}{msg.sender.last_name[:1]}".upper()
                    if msg.sender.first_name and msg.sender.last_name
                    else msg.sender.username[:2].upper()
                ),
                "avatar_color": get_user_color(msg.sender.id),
                "timestamp": msg.created_at.isoformat(),
                "is_sent": is_sent,
                "is_read": msg.is_read,
                "date": msg.created_at.strftime("%Y-%m-%d"),
            })

        employee = EmployeeProfile.objects.filter(user=other_user).first()

        return JsonResponse({
            "success": True,
            "messages": messages_data,
            "other_user": {
                "id": other_user.id,
                "name": other_user.get_full_name(),
                "initials": (
                    f"{other_user.first_name[:1]}{other_user.last_name[:1]}".upper()
                    if other_user.first_name and other_user.last_name
                    else other_user.username[:2].upper()
                ),
                "avatar_color": get_user_color(other_user.id),
                "job_position": employee.job_position if employee else "Team Member",
                "department": (
                    employee.department.name
                    if employee and employee.department else "No Department"
                ),
                "is_online": redis_exists(f"user_online_{other_user.id}"),
            }
        })

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"}, status=404)


@login_required
@require_POST
def send_message_api(request):
    """Send direct message"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get("recipient_id")
        content = data.get("content", "").strip()

        if not recipient_id or not content:
            return JsonResponse({"success": False, "error": "Missing fields"}, status=400)

        recipient = User.objects.get(id=recipient_id)

        cutoff = timezone.now() - timezone.timedelta(seconds=5)
        existing = Message.objects.filter(
            sender=request.user,
            content=content,
            message_type="direct",
            created_at__gte=cutoff,
        ).first()

        if existing:
            message = existing
            if not message.recipients.filter(id=recipient.id).exists():
                message.recipients.add(recipient)
        else:
            message = Message.objects.create(
                sender=request.user,
                content=content,
                message_type="direct",
                created_at=timezone.now(),
            )
            message.recipients.add(recipient)

        publish_message(message, request.user, recipient)

        return JsonResponse({
            "success": True,
            "message_id": message.id,
            "timestamp": message.created_at.isoformat(),
        })

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "Recipient not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def mark_as_read_api(request, user_id):
    """Mark messages as read"""
    Message.objects.filter(
        sender_id=user_id,
        recipients=request.user,
        is_read=False,
        message_type="direct"
    ).update(is_read=True)

    return JsonResponse({"success": True})


@login_required
@require_GET
def get_unread_count_api(request):
    unread_count = Message.objects.filter(
        recipients=request.user,
        is_read=False,
        message_type="direct"
    ).count()

    return JsonResponse({"success": True, "unread_count": unread_count})


@login_required
@require_POST
def start_conversation_api(request):
    try:
        data = json.loads(request.body)
        recipient = User.objects.get(id=data.get("recipient_id"))

        employee = EmployeeProfile.objects.filter(user=recipient).first()
        existing = Message.objects.filter(
            Q(sender=request.user, recipients=recipient, message_type="direct") |
            Q(sender=recipient, recipients=request.user, message_type="direct")
        ).exists()

        return JsonResponse({
            "success": True,
            "user_id": recipient.id,
            "name": recipient.get_full_name(),
            "initials": (
                f"{recipient.first_name[:1]}{recipient.last_name[:1]}".upper()
                if recipient.first_name and recipient.last_name
                else recipient.username[:2].upper()
            ),
            "avatar_color": get_user_color(recipient.id),
            "job_position": employee.job_position if employee else "Team Member",
            "is_online": redis_exists(f"user_online_{recipient.id}"),
            "has_existing_conversation": existing,
        })

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"}, status=404)


@login_required
@require_GET
def search_users_api(request):
    query = request.GET.get("q", "").strip().lower()

    if len(query) < 2:
        return JsonResponse({"success": True, "results": []})

    managed_projects = Project.objects.filter(project_manager=request.user)
    members = ProjectMember.objects.filter(
        project__in=managed_projects,
        is_active=True
    ).select_related("employee__user").distinct()

    results = []
    for member in members:
        user = member.employee.user
        if user.id == request.user.id:
            continue

        if query in user.get_full_name().lower() or query in user.email.lower():
            results.append({
                "id": user.id,
                "name": user.get_full_name(),
                "email": user.email,
                "job_position": member.employee.job_position,
                "project": member.project.name,
                "is_online": redis_exists(f"user_online_{user.id}"),
                "avatar_color": get_user_color(user.id),
            })

    return JsonResponse({"success": True, "results": results[:10]})


# =====================================================
# Redis publisher
# =====================================================
def publish_message(message, sender, recipient):
    payload = {
        "type": "direct_message",
        "message_id": message.id,
        "sender_id": sender.id,
        "sender_name": sender.get_full_name(),
        "recipient_id": recipient.id,
        "content": message.content,
        "timestamp": message.created_at.isoformat(),
        "avatar_color": get_user_color(sender.id),
        "initials": (
            f"{sender.first_name[:1]}{sender.last_name[:1]}".upper()
            if sender.first_name and sender.last_name
            else sender.username[:2].upper()
        ),
    }

    redis_publish(f"user_{recipient.id}", payload)
    redis_publish(f"user_{sender.id}", payload)
