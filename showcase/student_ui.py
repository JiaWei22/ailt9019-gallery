"""Read-only student presentation helpers. No business records are changed."""
from django.utils import timezone
from .models import EventConfig,Assignment,Project,ProjectSubmission,Ballot

def window_status(event,kind):
    cfg=EventConfig.objects.filter(event=event).first()
    start=getattr(cfg,kind+'_start',None);end=getattr(cfg,kind+'_end',None)
    label='Reviews' if kind=='review' else 'Voting'
    from .demo_mode import ignore_schedule
    if ignore_schedule() and cfg and event.opened and cfg.confirmed:
        return f'{label}: open.'
    if not start or not end:return f'{label}: dates to be announced.'
    stamp=lambda t:timezone.localtime(t).strftime('%Y-%m-%d %H:%M (Hong Kong)')
    now=timezone.now()
    if now>=end:return f'{label}: deadline passed — closed at {stamp(end)}.'
    if not event.opened or not cfg.confirmed:return f'{label}: not enabled by the course team.'
    if now<start:return f'{label}: not started — opens {stamp(start)}.'
    return f'{label}: open until {stamp(end)}.'

def review_progress(event,person):
    qs=Assignment.objects.filter(reviewer=person,project__event=event,active=True,project__published=True)
    count=qs.count();completed=qs.filter(review__isnull=False).count()
    return dict(assigned=count,completed=completed,required=3,awaiting=max(0,3-count),remaining=max(0,3-completed))

def dashboard(event,person):
    from .assignment_plans import eligible
    project=Project.objects.filter(event=event,team_id=person.student.team_id).first()
    receipt=ProjectSubmission.objects.filter(project=project).order_by('-pk').first() if project else None
    ballot=Ballot.objects.filter(event=event,reviewer=person).first()
    rows=ballot_receipt(ballot)
    return dict(review_progress(event,person),eligible=eligible(event,person),project=project,receipt=receipt,
                ballot=ballot,valid_votes=sum(row['eligible'] for row in rows),
                excluded_votes=sum(not row['eligible'] for row in rows))

def ballot_receipt(ballot):
    if not ballot:return []
    projects={p.pk:p for p in Project.objects.filter(event=ballot.event,pk__in=ballot.choices)}
    rows=[]
    for pk in ballot.choices:
        p=projects.get(pk)
        eligible=bool(p and p.published and (p.vote_reset_at is None or ballot.submitted>p.vote_reset_at))
        rows.append(dict(pk=pk,code=p.code if p else 'Unavailable',title=p.title if p else 'Unavailable project',eligible=eligible,
                         status='Counts toward awards' if eligible else 'Excluded from awards — withdrawn or saved before withdrawal'))
    return rows
