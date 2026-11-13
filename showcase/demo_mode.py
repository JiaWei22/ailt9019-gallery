from django.conf import settings

def ignore_schedule():
    return bool(getattr(settings, 'W13_LOCAL_DEMO', False)
                and getattr(settings, 'W13_DEMO_IGNORE_SCHEDULE', False))
