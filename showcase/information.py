"""Read-only activity and guides. Unannounced fields remain empty."""
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET
from .views import identity,page,event_for
from .authentication import staff_identity
from .models import Event,EventConfig

@require_GET
def activity(req):
    if not identity(req) and not staff_identity(req):return redirect('showcase:login')
    event=event_for(req)
    return page(req,'activity',event=event,events=Event.objects.order_by('pk'),config=EventConfig.objects.filter(event=event).first() if event else None)

@require_GET
def student_guide(req):
    if not identity(req) and not staff_identity(req):return redirect('showcase:login')
    return page(req,'student_guide',event=event_for(req))

@require_GET
def staff_guide(req):
    if not staff_identity(req):return HttpResponseForbidden()
    return page(req,'staff_guide',event=event_for(req))
