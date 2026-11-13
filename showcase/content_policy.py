from django.core import signing
from .models import EventConfig,Assignment,Review,Ballot,ProjectDetails,Audit

CONTENT_FIELDS=('title','description','short_description','video','demo_video')

def ensure_editable(project,values):
    config=EventConfig.objects.filter(event_id=project.event_id).first()
    if not config or not config.content_frozen:return
    changed=any(getattr(project,k)!=v for k,v in values.items() if k in CONTENT_FIELDS)
    for field in ('project_url', 'repository_url'):
        if field in values:
            old=ProjectDetails.objects.filter(project=project).first()
            changed=changed or (getattr(old, field) if old else '')!=values[field]
    if changed:raise ValueError('Project content is frozen for this event. Staff must explicitly unfreeze the activity before changing content.')

def publication_state(project):
    return {'project':project.pk,'event':project.event_id,'published':project.published,'vote_reset_at':str(project.vote_reset_at),
            'assignments':Assignment.objects.filter(project=project).count(),
            'active_assignments':Assignment.objects.filter(project=project,active=True).count(),
            'reviews':Review.objects.filter(assignment__project=project).count(),
            'votes':sum(project.pk in choices for choices in Ballot.objects.filter(event_id=project.event_id).values_list('choices',flat=True))}

def publication_preview(project):
    state=publication_state(project)
    return dict(state,token=signing.dumps(state,salt='w13-publication'),target=not project.published)

def set_publication(project,token,actor):
    try:
        old=signing.loads(token,salt='w13-publication',max_age=3600)
        if old!=publication_state(project):raise signing.BadSignature()
    except signing.BadSignature:raise ValueError('Publication or submission counts changed. Review publication impact again.')
    project.published=not old['published']
    if not project.published:
        from django.utils import timezone
        project.vote_reset_at=timezone.now()
    project.save(update_fields=['published','vote_reset_at'])
    if not project.published:
        Assignment.objects.filter(project=project,active=True).update(active=False)
    Audit.objects.create(action='publication changed',actor=actor,
                         details={'event':project.event_id,'project':project.pk,'before':old,'published':project.published})
