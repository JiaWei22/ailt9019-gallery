"""Preview and append-only assignment plans with reproducible tie breaking."""
import hashlib,json,random,secrets
from django.core import signing
from .models import EventConfig,Project,Assignment,Audit
from reviews.models import ReviewerIdentity

def participants(event):
    config=EventConfig.objects.filter(event=event).first()
    people=ReviewerIdentity.objects.select_related('student').order_by('pk')
    if config and config.participant_codes is not None:
        people=people.filter(code__in=config.participant_codes)
    return people

def eligible(event,identity):
    return participants(event).filter(pk=identity.pk).exists()

def build(event,seed):
    people=list(participants(event));projects=list(Project.objects.filter(event=event,published=True).order_by('pk'))
    existing=list(Assignment.objects.filter(project__event=event).order_by('pk').values_list('reviewer_id','project_id','active'))
    state={'people':[(p.pk,p.student.team_id) for p in people],
           'projects':[(p.pk,p.team_id) for p in projects],'existing':existing}
    fingerprint=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    rng=random.Random(seed);rng.shuffle(people)
    load={p.pk:0 for p in projects};assigned={}
    history={}
    for reviewer,project,active in existing:
        history.setdefault(reviewer,set()).add(project)
        if not active or project not in load:continue
        assigned.setdefault(reviewer,set()).add(project)
        if project in load:load[project]+=1
    added=[];rows=[];errors=[]
    for person in people:
        old=assigned.get(person.pk,set());needed=max(0,3-len(old))
        if len(old)>3:errors.append(f'{person.code}: already has more than three tasks; no tasks will be removed.')
        candidates=[p for p in projects if p.team_id!=person.student.team_id and p.pk not in history.get(person.pk,set())]
        if len(candidates)<needed:
            errors.append(f'{person.code}: needs {needed} additional tasks but only {len(candidates)} eligible published projects.')
            continue
        rng.shuffle(candidates);candidates.sort(key=lambda p:load[p.pk])
        chosen=candidates[:needed]
        for p in chosen:added.append([person.pk,p.pk]);load[p.pk]+=1
        rows.append({'code':person.code,'existing':len(old),'new':[p.pk for p in chosen],'new_codes':[p.code for p in chosen]})
    if not people:errors.append('No eligible participants.')
    return {'fingerprint':fingerprint,'added':added,'rows':rows,'loads':[{'project':p.pk,'code':p.code,'title':p.title,'count':load[p.pk]} for p in projects],'errors':errors,'seed':seed}

def preview(event):
    plan=build(event,secrets.randbits(64))
    plan['token']=signing.dumps({'event':event.pk,'seed':plan['seed'],'fingerprint':plan['fingerprint']},salt='w13-assignment') if not plan['errors'] else ''
    return plan

def confirm(event,token,actor):
    try:payload=signing.loads(token,salt='w13-assignment',max_age=3600)
    except signing.BadSignature:raise ValueError('Assignment preview expired or missing. Preview again.')
    if payload.get('event')!=event.pk:raise ValueError('Assignment preview belongs to another event.')
    plan=build(event,payload['seed'])
    if plan['fingerprint']!=payload['fingerprint']:raise ValueError('Participants, projects or assignments changed. Preview again.')
    if plan['errors']:raise ValueError(' '.join(plan['errors']))
    Assignment.objects.bulk_create([Assignment(reviewer_id=i,project_id=p) for i,p in plan['added']])
    Audit.objects.create(action='assignment plan applied',actor=actor,
                         details={'event':event.pk,'seed':plan['seed'],'added':plan['added']})
    return plan
