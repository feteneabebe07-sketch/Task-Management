from django import template

register = template.Library()


@register.filter
def divide(value, arg):
    try:
        return value / arg
    except (TypeError, ZeroDivisionError):
        return None


@register.filter(name='multiply')
def multiply(value, arg):
    try:
        return value * arg
    except (TypeError, ValueError):
        return None


@register.filter(name='status')
def status(qs, status_value):
    if qs is None:
        return []
    try:
        # If it's a Django QuerySet, use ORM filtering
        if hasattr(qs, 'filter'):
            return qs.filter(status=status_value)
        # Fallback to pythonic filtering for lists/iterables
        return [item for item in qs if getattr(item, 'status', None) == status_value]
    except Exception:
        return []


@register.filter(name='status_in')
def status_in(qs, statuses):
    if qs is None:
        return []
    if isinstance(statuses, str):
        status_list = [s.strip() for s in statuses.split(',') if s.strip()]
    else:
        status_list = list(statuses)
    try:
        if hasattr(qs, 'filter'):
            return qs.filter(status__in=status_list)
        return [item for item in qs if getattr(item, 'status', None) in status_list]
    except Exception:
        return []


@register.filter(name='priority')
def priority(qs, p):
    if qs is None:
        return []
    try:
        if hasattr(qs, 'filter'):
            return qs.filter(priority=p)
        return [item for item in qs if getattr(item, 'priority', None) == p]
    except Exception:
        return []


@register.filter(name='due_between')
def due_between(qs, start, end=None):
    # Template can pass two args like: |due_between:today:week_end
    if qs is None:
        return []
    try:
        if end is None:
            return qs
        if hasattr(qs, 'filter'):
            return qs.filter(due_date__gte=start, due_date__lte=end)
        return [item for item in qs if getattr(item, 'due_date', None) is not None and start <= item.due_date <= end]
    except Exception:
        return []


@register.filter(name='due_date')
def due_date(qs, date_val):
    if qs is None:
        return []
    try:
        if hasattr(qs, 'filter'):
            return qs.filter(due_date=date_val)
        return [item for item in qs if getattr(item, 'due_date', None) == date_val]
    except Exception:
        return []


@register.filter(name='split')
def split(value, sep=','):
    if value is None:
        return []
    try:
        return value.split(sep)
    except Exception:
        return []


@register.simple_tag
def filter_tasks_between(qs, start, end, statuses=None):
    if qs is None:
        return []
    try:
        # initial range filter
        if hasattr(qs, 'filter'):
            result = qs.filter(due_date__gte=start, due_date__lte=end)
        else:
            result = [item for item in qs if getattr(item, 'due_date', None) is not None and start <= item.due_date <= end]

        # apply status filtering if provided
        if statuses:
            if isinstance(statuses, str):
                status_list = [s.strip() for s in statuses.split(',') if s.strip()]
            else:
                status_list = list(statuses)

            if hasattr(result, 'filter'):
                result = result.filter(status__in=status_list)
            else:
                result = [item for item in result if getattr(item, 'status', None) in status_list]

        return result
    except Exception:
        return []


@register.simple_tag
def current_date():
    import datetime
    return datetime.date.today()


@register.simple_tag
def week_end(days=7):
    import datetime
    return datetime.date.today() + datetime.timedelta(days=int(days))