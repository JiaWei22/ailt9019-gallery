import csv,io,re,random
from urllib.parse import urlparse,parse_qs,urlencode
from django.urls import reverse
from django.middleware.csrf import rotate_token
from django.shortcuts import render,redirect,get_object_or_404
from django.http import HttpResponse,HttpResponseForbidden,Http404
from .authentication import staff_identity,sign_in,permitted_attempt
from .models import StaffAccount
from django.db import transaction,OperationalError
from django.utils import timezone
from django.conf import settings
from reviews.models import ReviewerIdentity,Team
from reviews.services import authenticate_student
from .models import Event,Project,Assignment,Review,Ballot,Audit,EventConfig
from .student_revisions import issue as issue_revision, check as check_revision, RevisionConflict
LIMITS=[2,3,2,2,1]
LABELS=['User value','Working system','Evidence','Communication','Constructive comment']
def event_url(name,event_id):
 return reverse('showcase:'+name)+'?'+urlencode({'event':event_id})
def identity(req):
 if staff_identity(req):return None
 return ReviewerIdentity.objects.select_related('student').filter(pk=req.session.get('w13_identity')).first()
def page(req,t,**ctx):
 help_event=ctx.get('event') or getattr(ctx.get('project'),'event',None) or getattr(getattr(ctx.get('assignment'),'project',None),'event',None)
 ctx.setdefault('help_event',help_event)
 ctx.setdefault('nav_event',help_event)
 from .student_ui import window_status,ballot_receipt
 if t=='review':
  old=ctx.get('old');ctx['saved_scores']=list(zip(LABELS,old.scores,LIMITS)) if old else []
  ctx['strength_value']=req.POST.get('strength','') if req.method=='POST' else (old.strength if old else '')
  ctx['improvement_value']=req.POST.get('improvement','') if req.method=='POST' else (old.improvement if old else '')
  ctx['window_message']=window_status(help_event,'review')
  ctx['revision']=req.POST.get('revision','') if req.method=='POST' else issue_revision('review',identity(req).pk,ctx['assignment'].pk,old)
  ctx['reload_url']=reverse('showcase:review',args=[ctx['assignment'].pk])
  if old and not help_event.eventconfig.allow_review_edit:
   ctx['closed']=True
   ctx['edit_message']='Review editing is disabled. Your saved review still counts while this task is active.'
  from .assignment_plans import eligible
  if not eligible(help_event,identity(req)):
   ctx['closed']=True
   ctx['edit_message']='You are not a participant in this event. Existing records are read-only; contact course staff.'
 if t=='vote' and ctx.get('event'):
  ctx['window_message']=window_status(ctx['event'],'vote')
  ctx['ballot_rows']=ballot_receipt(ctx.get('ballot'))
  ctx['revision']=(req.POST.get('revision','') if req.method=='POST' else req.GET.get('revision','') if req.GET.get('draft')=='1' else issue_revision('ballot',identity(req).pk,ctx['event'].pk,ctx.get('ballot')))
  ctx['reload_url']=event_url('vote',ctx['event'].pk)
  if ctx.get('ballot') and ctx.get('config') and not ctx['config'].allow_vote_edit:
   ctx['closed']=True
   ctx['edit_message']='Ballot editing is disabled. Your saved ballot is shown above.'
  from .assignment_plans import eligible
  if not eligible(ctx['event'],identity(req)):
   ctx['closed']=True
   ctx['edit_message']='You are not a participant in this event. Existing records are read-only; contact course staff.'
  available={p.pk for p in ctx.get('projects',[])}
  ctx['selected']=list(dict.fromkeys(int(x) for x in ctx.get('selected',[]) if str(x).isdecimal() and int(x) in available))
 from .authentication import session_marker
 ctx['session_marker']=session_marker(req)
 from .demo_mode import ignore_schedule
 return render(req,'showcase/'+t+'.html',dict(local_demo=getattr(settings,'W13_LOCAL_DEMO',False),demo_ignore_schedule=ignore_schedule(),who=identity(req),staff=staff_identity(req),external_video_enabled=getattr(settings,'W13_EXTERNAL_VIDEO_ENABLED',False),**ctx))
def event_for(req):
 value=req.POST.get('event') or req.GET.get('event')
 if value and not value.isdecimal():raise Http404()
 return get_object_or_404(Event,pk=value) if value else Event.objects.first()
def active(event,kind='review'):
 config=EventConfig.objects.filter(event=event).first()
 if config is None:return False
 from .demo_mode import ignore_schedule
 if ignore_schedule():return bool(event.opened and config.confirmed)
 start=getattr(config,kind+'_start');end=getattr(config,kind+'_end')
 return bool(event.opened and config.confirmed and start and end and start<=timezone.now()<end)
def login(req):
 error=''
 if req.method=='POST':
  try:
   if not permitted_attempt(req,'student',req.POST.get('account','')):
    return HttpResponse('Too many attempts. Wait one minute.',status=429,headers={'Retry-After':'60'})
   i,_=authenticate_student(req.POST.get('account',''),req.POST.get('password',''))
   if i:
    req.session.cycle_key()
    rotate_token(req)
    req.session.pop('w13_staff',None)
    req.session.pop('w13_staff_signature',None)
    req.session['w13_identity']=i.pk
    return redirect('showcase:gallery')
   error='Wrong account or password.'
  except OperationalError:
   return HttpResponse('Busy. Please retry.',status=503)
 return page(req,'login',error=error)
def logout(req):
 if req.method=='POST':
  req.session.pop('w13_identity',None)
  rotate_token(req)
 return redirect('showcase:login')
def gallery(req):
 if not identity(req):return redirect('showcase:login')
 event=event_for(req)
 ps=Project.objects.filter(published=True,event=event).select_related('team').order_by('number');q=req.GET.get('q','').strip()
 if q:
  from django.db.models import Q
  match=Q(title__icontains=q)|Q(team__name__icontains=q)
  code=q.strip().upper().lstrip('#')
  candidates=[p.pk for p in ps if p.code==code or (code.isdecimal() and p.number==int(code))]
  ps=ps.filter(match|Q(pk__in=candidates))
 from .student_ui import dashboard
 return page(req,'gallery',projects=ps,q=q,event=event,events=Event.objects.all(),todo=dashboard(event,identity(req)) if event else None)
def project(req,pk):
 i=identity(req)
 if not i:return redirect('showcase:login')
 p=get_object_or_404(Project,pk=pk,published=True)
 return page(req,'project',project=p,assignment=Assignment.objects.filter(reviewer=i,project=p,active=True).first())
def tasks(req):
 i=identity(req)
 if not i:return redirect('showcase:login')
 event=event_for(req)
 tasks=Assignment.objects.filter(reviewer=i,project__event=event).select_related('project__event','project__event__eventconfig','review')
 if req.GET.get('event'):tasks=tasks.filter(project__event=event_for(req))
 from django.db.models import F
 tasks=tasks.order_by('-active','-project__published',F('review__submitted').asc(nulls_first=True),'project__number')
 current=tasks.filter(active=True,project__published=True)
 from .student_ui import review_progress,window_status
 return page(req,'tasks',event=event,events=Event.objects.all(),tasks=tasks,total=3,completed=current.filter(review__isnull=False).count(),progress=review_progress(event,i),window_message=window_status(event,'review'))
def review(req,pk):
 i=identity(req)
 if not i:return redirect('showcase:login')
 a=get_object_or_404(Assignment.objects.select_related('project'),pk=pk,reviewer=i)
 error=''; conflict=False; old=Review.objects.filter(assignment=a).first()
 if not a.active or not a.project.published:
  response=page(req,'review',assignment=a,old=old,closed=True,withdrawn=True)
  if req.method=='POST':response.status_code=403
  return response
 if req.method=='POST':
  try:
   with transaction.atomic():
    Event.objects.filter(pk=a.project.event_id).update(opened=models_open(a.project.event_id))
    e=Event.objects.get(pk=a.project.event_id)
    if not active(e):raise ValueError('Review window is closed.')
    from .assignment_plans import eligible
    if not eligible(e,i):raise ValueError('You are not a participant in this event.')
    if not Assignment.objects.filter(pk=a.pk,active=True,project__published=True).exists():raise ValueError('Project is no longer published.')
    old=Review.objects.filter(assignment=a).first()
    check_revision(req.POST.get('revision',''),'review',i.pk,a.pk,old)
    if old and not EventConfig.objects.get(event=e).allow_review_edit:raise ValueError('Review editing is disabled.')
    scores=[int(req.POST.get('score'+str(k),'-1')) for k in range(5)]
    if any(not 0<=x<=m for x,m in zip(scores,LIMITS)):raise ValueError('Invalid score range.')
    strength=req.POST.get('strength','').strip();improvement=req.POST.get('improvement','').strip()
    if not strength or not improvement:raise ValueError('Both comments are required.')
    if old:Audit.objects.create(action='review revision',actor=i.code,details={'assignment':a.pk,'scores':old.scores,'strength':old.strength,'improvement':old.improvement})
    Review.objects.update_or_create(assignment=a,defaults=dict(scores=scores,strength=strength,improvement=improvement))
   return redirect(event_url('tasks',a.project.event_id))
  except (ValueError,OperationalError) as exc:
   error=str(exc) if isinstance(exc,ValueError) else 'Busy. Please retry.'
   conflict=isinstance(exc,RevisionConflict)
 response=page(req,'review',assignment=a,old=old,error=error,fields=[(k,label,limit,req.POST.get('score'+str(k),old.scores[k] if old else '')) for k,(label,limit) in enumerate(zip(LABELS,LIMITS))],closed=not active(a.project.event),conflict=conflict)
 if conflict:response.status_code=409
 return response
def models_open(pk):
 from django.db.models import F
 return F('opened')
def vote_preview(req):
 if req.method!='POST':return HttpResponse(status=405,headers={'Allow':'POST'})
 i=identity(req)
 if not i:return redirect('showcase:login')
 e=event_for(req)
 if not e:raise Http404()
 config=EventConfig.objects.filter(event=e).first()
 ps=Project.objects.filter(event=e,published=True)
 if not config or not config.allow_self_vote:ps=ps.exclude(team=i.student.team)
 ids=[]
 try:
  if not active(e,'vote'):raise ValueError('Voting is closed.')
  from .assignment_plans import eligible
  if not eligible(e,i):raise ValueError('You are not a participant in this event.')
  ids=[int(x) for x in req.POST.getlist('choices')]
  if not 1<=len(ids)<=3 or len(set(ids))!=len(ids):raise ValueError('Choose 1–3 different projects.')
  if ps.filter(pk__in=ids).count()!=len(ids):raise ValueError('Invalid project selection.')
  previous=Ballot.objects.filter(event=e,reviewer=i).first()
  check_revision(req.POST.get('revision',''),'ballot',i.pk,e.pk,previous)
  if previous and not config.allow_vote_edit:raise ValueError('Ballot editing is disabled.')
 except ValueError as exc:
  response=page(req,'vote',event=e,events=Event.objects.all(),config=config,projects=ps,ballot=Ballot.objects.filter(event=e,reviewer=i).first(),selected=ids,error=str(exc),closed=not active(e,'vote'),conflict=isinstance(exc,RevisionConflict))
  if isinstance(exc,RevisionConflict):response.status_code=409
  return response
 return page(req,'vote_preview',event=e,choices=ps.filter(pk__in=ids),previous=previous,revision=req.POST.get('revision',''),back_url=event_url('vote',e.pk)+'&'+urlencode({'draft':'1','choices':ids,'revision':req.POST.get('revision','')},doseq=True))
def vote(req):
 i=identity(req)
 if not i:return redirect('showcase:login')
 e=event_for(req);error='';conflict=False
 if not e:return page(req,'vote',error='No event.',projects=[])
 ps=Project.objects.filter(event=e,published=True)
 config=EventConfig.objects.filter(event=e).first()
 if not config or not config.allow_self_vote:ps=ps.exclude(team=i.student.team)
 if req.method=='POST':
  try:
   with transaction.atomic():
    Event.objects.filter(pk=e.pk).update(opened=models_open(e.pk))
    e.refresh_from_db()
    if not active(e,'vote'):raise ValueError('Voting is closed.')
    from .assignment_plans import eligible
    if not eligible(e,i):raise ValueError('You are not a participant in this event.')
    config=EventConfig.objects.get(event=e)
    ps=Project.objects.filter(event=e,published=True)
    if not config.allow_self_vote:ps=ps.exclude(team=i.student.team)
    ids=[int(x) for x in req.POST.getlist('choices')]
    if not 1<=len(ids)<=3 or len(set(ids))!=len(ids):raise ValueError('Choose 1–3 different projects.')
    if ps.filter(pk__in=ids).count()!=len(ids):raise ValueError('Invalid project selection.')
    previous=Ballot.objects.filter(event=e,reviewer=i).first()
    check_revision(req.POST.get('revision',''),'ballot',i.pk,e.pk,previous)
    if previous and not config.allow_vote_edit:raise ValueError('Ballot editing is disabled.')
    Audit.objects.create(action='ballot change',actor=i.code,details={'previous':previous.choices if previous else [],'new':ids})
    Ballot.objects.update_or_create(event=e,reviewer=i,defaults={'choices':ids})
   return redirect(event_url('vote',e.pk))
  except (ValueError,OperationalError) as exc:
   error=str(exc) if isinstance(exc,ValueError) else 'Busy. Please retry.'
   conflict=isinstance(exc,RevisionConflict)
 b=Ballot.objects.filter(event=e,reviewer=i).first()
 response=page(req,'vote',event=e,events=Event.objects.all(),config=config,projects=ps,ballot=b,selected=(req.POST.getlist('choices') if req.method=='POST' else req.GET.getlist('choices') if req.GET.get('draft')=='1' else b.choices if b else []),error=error,closed=not active(e,'vote'),conflict=conflict)
 if conflict:response.status_code=409
 return response
def video_id(url):
 u=urlparse(url); host=(u.hostname or '').lower()
 if u.scheme!='https':raise ValueError('HTTPS YouTube link required.')
 value=u.path.strip('/') if host=='youtu.be' else parse_qs(u.query).get('v',[''])[0] if host in ['youtube.com','www.youtube.com'] and u.path=='/watch' else ''
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',value):raise ValueError('Invalid YouTube link.')
 return value
def manage(req):
 error=''
 if not staff_identity(req):
  if req.method=='POST':
   try:
    if not permitted_attempt(req,'staff',req.POST.get('username','')):
     return HttpResponse('Too many attempts. Wait one minute.',status=429,headers={'Retry-After':'60'})
    user=StaffAccount.objects.filter(username=req.POST.get('username',''),enabled=True).first()
    if user and user.check_password(req.POST.get('password','')):
     sign_in(req,user);return redirect('showcase:manage')
   except OperationalError:
    return HttpResponse('Busy. Please retry.',status=503)
   error='Wrong staff credentials.'
  return page(req,'staff_login',error=error)
 if req.method=='POST':
  e=event_for(req);action=req.POST.get('action')
  try:
   with transaction.atomic():
    if not e:raise ValueError('No event configured.')
    Event.objects.filter(pk=e.pk).update(opened=models_open(e.pk))
    if action=='publish':
     from .content_policy import publication_preview,set_publication
     p=get_object_or_404(Project,pk=req.POST.get('project'),event=e)
     if not req.POST.get('confirm'):
      return page(req,'publication_preview',project=p,event=e,impact=publication_preview(p))
     set_publication(p,req.POST.get('preview_token',''),staff_identity(req).username)
    elif action=='close':e.opened=False;e.save()
    elif action=='assign':
     from .assignment_plans import preview,confirm
     if not req.POST.get('confirm'):
      return page(req,'assignment_preview',event=e,plan=preview(e))
     confirm(e,req.POST.get('preview_token',''),staff_identity(req).username)
    elif action=='import':
     from .importing import prepare,preview_token,confirm
     e.refresh_from_db()
     source=req.POST.get('csv','')
     prepared,errors=prepare(e,source)
     if errors or not req.POST.get('confirm'):
      return page(req,'preview',rows=prepared,event=e,csv=source,errors=errors,preview_token=preview_token(e,prepared) if not errors else '')
     confirm(e,prepared,req.POST.get('preview_token',''),staff_identity(req).username)
    else:raise ValueError('Unsupported action.')
    Audit.objects.create(action=action,actor=staff_identity(req).username,details={'event':e.pk,'project':req.POST.get('project')})
   return redirect(event_url('manage',e.pk))
  except (ValueError,KeyError,Team.DoesNotExist) as exc:error=str(exc)
  except OperationalError:return HttpResponse('Busy. No changes saved. Please retry.',status=503,headers={'Retry-After':'2'})
 e=event_for(req)
 from .reporting import progress,vote_totals,team_submissions
 return page(req,'manage',team_submissions=team_submissions(e),progress=progress(e),vote_totals=vote_totals(e),projects=Project.objects.filter(event=e).select_related('team','projectdetails'),published_count=Project.objects.filter(event=e,published=True).count(),events=Event.objects.all(),event=e,review_count=Review.objects.filter(assignment__project__event=e).count(),ballot_count=Ballot.objects.filter(event=e).count(),error=error)
def export(req):
 actor=staff_identity(req)
 if not actor:return HttpResponseForbidden()
 e=event_for(req)
 if not e:raise Http404()
 kind=req.GET.get('kind','reviews')
 if kind not in ['reviews','votes','progress','submissions']:raise Http404()
 if not getattr(settings,'W13_WRITES_ENABLED',False):
  return HttpResponse('Audited exports are unavailable while W13 is read-only.',status=503)
 from .reporting import csv_safe,progress,vote_totals,team_submissions
 try:
  with transaction.atomic():
   # Audit is the first write: export reads a consistent SQLite snapshot.
   entry=Audit.objects.create(action='export',actor=actor.username,details={'event':e.pk,'kind':kind})
   out=HttpResponse(content_type='text/csv; charset=utf-8')
   out['Content-Disposition']=f'attachment; filename="w13-event-{e.pk}-{kind}.csv"'
   out['Cache-Control']='no-store'
   writer=csv.writer(out)
   def row(values):writer.writerow([csv_safe(v) for v in values])
   count=0
   if kind=='submissions':
    row(['event_id','team_id','team_name','status','project_id','project_title','published','last_student_submission','receipt'])
    for item in team_submissions(e):
     p=item['project'];receipt=item['receipt']
     row([e.pk,item['team'].pk,item['team'].name,item['status'],p.pk if p else '',p.title if p else '',p.published if p else False,timezone.localtime(receipt.submitted_at).isoformat() if receipt else '',receipt.request_key if receipt else '']);count+=1
   elif kind=='votes':
    row(['event_id','event_title','project_id','project_title','published','votes','recorded_votes','excluded_votes'])
    for item in vote_totals(e):
     p=item['project'];row([e.pk,e.title,p.pk,p.title,p.published,item['votes'],item['recorded_votes'],item['excluded_votes']]);count+=1
   elif kind=='progress':
    row(['event_id','event_title','reviewer_id','assigned','completed','ballot_submitted'])
    for item in progress(e):
     row([e.pk,e.title,item['reviewer'],item['assigned'],item['completed'],item['voted']]);count+=1
   else:
    row(['event_id','event_title','project_id','project_title','reviewer_id','user_value','working_system','evidence','communication','constructive_comment','total','strength','improvement','submitted_at','assignment_id','assignment_active','project_published','reviewer_eligible','counts_toward_completion'])
    from .assignment_plans import participants
    eligible_ids=set(participants(e).values_list('pk',flat=True))
    for x in Review.objects.filter(assignment__project__event=e).select_related('assignment__reviewer','assignment__project').order_by('pk'):
     a=x.assignment
     included=bool(a.active and a.project.published and a.reviewer_id in eligible_ids)
     row([e.pk,e.title,a.project_id,a.project.title,a.reviewer.code,*x.scores,sum(x.scores),x.strength,x.improvement,timezone.localtime(x.submitted).isoformat(),a.pk,a.active,a.project.published,a.reviewer_id in eligible_ids,included]);count+=1
   entry.details['rows']=count;entry.save(update_fields=['details'])
  return out
 except OperationalError:return HttpResponse('Busy. Export not completed. Please retry.',status=503)

def staff_logout(req):
 if req.method=='POST':
  req.session.pop('w13_staff',None)
  req.session.pop('w13_staff_signature',None)
  rotate_token(req)
 return redirect('showcase:manage')


def session_state(req):
 from django.http import JsonResponse
 from .authentication import session_marker
 return JsonResponse({'marker':session_marker(req)})
