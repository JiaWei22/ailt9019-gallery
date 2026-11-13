from django.conf import settings

from .models import ReviewerIdentity


def current_reviewer(request):
    pk = request.session.get(settings.SESSION_REVIEWER_KEY)
    reviewer = ReviewerIdentity.objects.filter(pk=pk).first() if pk else None
    return {
        "current_reviewer": reviewer,
        "is_staff_session": bool(request.session.get(settings.SESSION_STAFF_KEY)),
    }
