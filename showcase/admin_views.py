import hashlib
import json
from django.core import signing
from django.shortcuts import get_object_or_404,redirect
from django.http import HttpResponseForbidden,Http404,HttpResponse
from django.db import transaction,OperationalError
from django.db.models import F
from django.utils import timezone
from .models import Event,EventConfig,Project,ProjectDetails,Audit
from .authentication import staff_identity
from .forms import EventForm,ProjectForm
from .views import page,video_id,event_url


def state_of(obj,details):
    def fields(instance):
        return {f.attname:str(getattr(instance,f.attname)) for f in instance._meta.fields} if instance else {}
    return {'object':fields(obj),'configuration':fields(details)}


def revision_for(obj,details):
    data=json.dumps(state_of(obj,details),sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def edit(req,kind,pk):
    if not staff_identity(req):return HttpResponseForbidden()
    if kind not in ['event','project']:raise Http404()
    is_event=kind=='event'
    obj=get_object_or_404(Event if is_event else Project,pk=pk)
    event_id=obj.pk if is_event else obj.event_id

    def prepare(obj):
        model=EventConfig if is_event else ProjectDetails
        ref={'event':obj} if is_event else {'project':obj}
        details=model.objects.filter(**ref).first()
        initial={'title':obj.title,'opened':obj.opened} if is_event else {
            'title':obj.title,'description':obj.description,'short_description':obj.short_description,
            'demo_youtube_url':('https://youtu.be/'+obj.demo_video) if obj.demo_video else '',
            'youtube_url':('https://youtu.be/'+obj.video) if obj.video else ''}
        if is_event:initial['participant_codes']=' '.join(details.participant_codes or []) if details else ''
        initial['revision']=signing.dumps({'kind':kind,'pk':pk,'hash':revision_for(obj,details)},salt='w13-edit')
        form=(EventForm if is_event else ProjectForm)(req.POST if req.method=='POST' else None,instance=details,initial=initial)
        return details,ref,form

    def display(form,status=200,error=''):
        response=page(req,'edit',form=form,error=error,reload_url=req.path,event=(obj if is_event else obj.event),
                      heading=('Configure event' if is_event else 'Edit project')+' · '+obj.title)
        response.status_code=status
        return response

    if req.method!='POST':
        return display(prepare(obj)[2])
    try:
        with transaction.atomic():
            # First DB operation in this transaction: serialize all activity writes.
            Event.objects.filter(pk=event_id).update(opened=F('opened'))
            actor=staff_identity(req)
            if not actor:return HttpResponseForbidden()
            obj=get_object_or_404(Event if is_event else Project,pk=pk)
            details,ref,form=prepare(obj)
            before=state_of(obj,details)
            try:
                revision=signing.loads(req.POST.get('revision',''),salt='w13-edit',max_age=3600)
                current={'kind':kind,'pk':pk,'hash':revision_for(obj,details)}
                if revision!=current:raise signing.BadSignature('stale')
            except signing.BadSignature:
                return display(form,409,'This form has expired or another change was saved. Reload the latest version and review your changes before saving.')
            if not form.is_valid():return display(form)
            d=form.save(commit=False)
            for key,value in ref.items():setattr(d,key,value)
            obj.title=form.cleaned_data['title']
            if is_event:
                obj.opened=form.cleaned_data['opened']
                ends=[x for x in (d.review_end,d.vote_end) if x is not None]
                if ends:obj.deadline=max(ends)
            else:
                from .content_policy import ensure_editable
                candidate={k:form.cleaned_data[k] for k in ['title','description','short_description','project_url','repository_url']}
                candidate['demo_video']=video_id(form.cleaned_data['demo_youtube_url']) if form.cleaned_data['demo_youtube_url'] else ''
                candidate['video']=video_id(form.cleaned_data['youtube_url']) if form.cleaned_data['youtube_url'] else ''
                # Restore the saved title for comparison: the form title has not been persisted.
                saved_title=before['object']['title']
                proposed_title=obj.title;obj.title=saved_title
                try:ensure_editable(obj,candidate)
                except ValueError as exc:return display(form,409,str(exc))
                obj.title=proposed_title
                obj.description=form.cleaned_data['description']
                obj.short_description=form.cleaned_data['short_description']
                new=video_id(form.cleaned_data['youtube_url']) if form.cleaned_data['youtube_url'] else ''
                from .materials import reset_changed_checks
                reset_changed_checks(d, (obj.video, obj.demo_video), (new, candidate['demo_video']))
                for prefix in ('presentation', 'demo'):
                    setattr(d, prefix + '_checked_at', timezone.now() if getattr(d, prefix + '_status') != 'unchecked' else None)
                obj.video=new
                obj.demo_video=candidate['demo_video']
            obj.save();d.save()
            Audit.objects.create(action=kind+' edit',actor=actor.username,
                                 details={'id':obj.pk,'event':event_id,'before':before,'after':state_of(obj,d)})
        return redirect(event_url('manage',event_id))
    except OperationalError:
        return HttpResponse('Busy. No edit was saved. Please retry.',status=503,headers={'Retry-After':'2'})


def audit(req):
    if not staff_identity(req):return HttpResponseForbidden()
    return page(req,'audit',entries=Audit.objects.order_by('-pk')[:200])
