"""Team-scoped direct publication. All writes are confined to showcase tables."""
import uuid
from django.core import signing
from django.db import transaction, OperationalError
from django.db.models import F
from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import Event, EventConfig, Project, ProjectDetails, ProjectSubmission, Audit
from .forms import StudentProjectForm
from .views import identity, page, event_for, event_url, video_id
from .admin_views import revision_for
from .assignment_plans import eligible


def closed_reason(config, project=None):
    if project and not project.published and project.vote_reset_at is not None:
        return 'Course staff withdrew this project. Contact staff to restore publication before submitting changes.'
    if not config or not config.confirmed or not config.submissions_enabled:
        return 'Project submissions are not enabled for this event.'
    if config.content_frozen:
        return 'Project content is frozen.'
    from .demo_mode import ignore_schedule
    if ignore_schedule():return ''
    if not config.submission_deadline or timezone.now() >= config.submission_deadline:
        return 'The submission deadline has passed or has not been configured.'
    if config.review_start and timezone.now() >= config.review_start:
        return 'Reviews have started. Project submissions are closed.'
    return ''


@require_http_methods(['GET', 'POST'])
def my_project(req):
    person = identity(req)
    if not person:
        return redirect('showcase:login')
    if req.method == "POST":
        return HttpResponseForbidden("Submit both video links on Moodle. Only course staff can publish Gallery projects.")
    event = event_for(req)
    if not event:
        return HttpResponse('No event is available.', status=404)

    config = EventConfig.objects.filter(event=event).first()
    project = Project.objects.filter(event=event, team_id=person.student.team_id).first()
    return page(req, "moodle_submission", event=event, config=config, project=project)
