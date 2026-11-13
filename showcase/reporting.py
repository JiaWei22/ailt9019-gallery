"""Activity-scoped aggregate views; no real names, UIDs or credentials."""
from collections import Counter
from django.db.models import Count,Q
from .assignment_plans import participants
from .models import Assignment,Ballot,Project

def progress(event):
    people=list(participants(event))
    counts={r['reviewer_id']:r for r in Assignment.objects.filter(project__event=event,active=True,project__published=True).values('reviewer_id').annotate(assigned=Count('pk'),completed=Count('review',filter=Q(review__isnull=False)))}
    voted=set(Ballot.objects.filter(event=event).values_list('reviewer_id',flat=True))
    return [{'reviewer':p.code,'assigned':counts.get(p.pk,{}).get('assigned',0),
             'completed':counts.get(p.pk,{}).get('completed',0),'voted':p.pk in voted} for p in people]

def vote_totals(event):
    projects=list(Project.objects.filter(event=event).order_by('pk'))
    counts=Counter();raw=Counter();by_id={p.pk:p for p in projects}
    for ballot in Ballot.objects.filter(event=event):
        for pk in set(ballot.choices):
            project=by_id.get(pk)
            if project is None:continue
            raw[pk]+=1
            if project.published and (project.vote_reset_at is None or ballot.submitted>project.vote_reset_at):
                counts[pk]+=1
    return [{'project':p,'votes':counts[p.pk],'recorded_votes':raw[p.pk],
             'excluded_votes':raw[p.pk]-counts[p.pk]} for p in projects]

def csv_safe(value):
    text=str(value)
    # Leading whitespace/control characters must not hide spreadsheet formulas.
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text


def team_submissions(event):
    """Eligible teams only; imported projects are not student submission receipts."""
    from reviews.models import Team
    from .models import ProjectSubmission
    teams=Team.objects.filter(pk__in=participants(event).values_list('student__team_id',flat=True)).order_by('pk')
    projects={p.team_id:p for p in Project.objects.filter(event=event)}
    receipts={}
    for receipt in ProjectSubmission.objects.filter(project__event=event).order_by('-pk'):
        receipts.setdefault(receipt.project_id,receipt)
    result=[]
    for team in teams:
        project=projects.get(team.pk)
        receipt=receipts.get(project.pk) if project else None
        status=('Published in Gallery' if project.published else 'Awaiting staff publication') if project else 'Awaiting staff import'
        result.append(dict(team=team,project=project,receipt=receipt,status=status))
    return result
