"""Spatial Gallery sharing the existing publication and ballot rules."""
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET
from .views import identity,event_for,page,active
from .models import Project,EventConfig,Ballot
from .student_revisions import issue
from .assignment_plans import eligible

@require_GET
def exhibition(request, prototype=False):
    person=identity(request)
    if not person:return redirect('showcase:login')
    event=event_for(request)
    config=EventConfig.objects.filter(event=event).first() if event else None
    ballot=Ballot.objects.filter(event=event,reviewer=person).first() if event else None
    projects=list(Project.objects.filter(event=event,published=True).select_related('team').order_by('number'))
    can_vote=bool(event and config and active(event,'vote') and eligible(event,person) and (not ballot or config.allow_vote_edit))
    data=[dict(id=p.pk,code=p.code,number=p.number,title=p.title,team=p.team.name,summary=p.short_description or p.description[:160],presentation_video=p.video,demo_video=p.demo_video,url=reverse('showcase:exhibit_detail',args=[p.pk]),canVote=bool(config and (config.allow_self_vote or p.team_id!=person.student.team_id))) for p in projects]
    selected=[pk for pk in (ballot.choices if ballot else []) if any(p['id']==pk and p['canVote'] for p in data)]
    return page(request,'openvgal' if prototype else 'exhibition',event=event,projects=data,exhibits=data[:5] if prototype else data,selected=selected,can_vote=can_vote,revision=issue('ballot',person.pk,event.pk,ballot) if event else '',ballot=ballot)

from django.shortcuts import get_object_or_404
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import Assignment

@require_GET
@xframe_options_sameorigin
def exhibit_detail(request,pk):
    person=identity(request)
    if not person:
        response=page(request,'exhibit_unavailable')
        response.status_code=401
        return response
    project=get_object_or_404(Project,pk=pk,published=True)
    return page(request,'exhibit_detail',project=project,assignment=Assignment.objects.filter(reviewer=person,project=project,active=True).first())

from django.http import FileResponse
from pathlib import Path
@require_GET
def phaser_asset(request):
    return FileResponse(open(Path(__file__).parent/'static/showcase/vendor/phaser-3.90.0.min.js','rb'),content_type='application/javascript')


@require_GET
def openvgal(request):
    return exhibition(request, prototype=True)

@require_GET
def openvgal_asset(request, name):
    # Explicit allowlist: never expose arbitrary files or the cloned repository.
    assets = {'babylon.js':'application/javascript',
              'babylonjs.loaders.min.js':'application/javascript',
              'hall.glb':'model/gltf-binary', 'hall.js':'application/javascript',
              'hall.css':'text/css', 'LICENSE.txt':'text/plain'}
    from django.http import Http404
    if name not in assets: raise Http404
    return FileResponse(open(Path(__file__).parent/'static/showcase/openvgal'/name,'rb'),content_type=assets[name])

@require_GET
def exhibition_asset(request, name):
    from django.http import Http404
    types={'exhibition-polished.js':'application/javascript','exhibition-polished.css':'text/css'}
    if name not in types:raise Http404
    return FileResponse(open(Path(__file__).parent/'static/showcase'/name,'rb'),content_type=types[name])
