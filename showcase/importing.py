"""Validated, explicit, preview-first W13 imports. Never writes roster records."""
import csv,io,hashlib,json
from django.core import signing
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from .models import Project,ProjectDetails,Audit
from reviews.models import Team

class ImportErrorDetail(ValueError):
    pass

def prepare(event,text):
    from .views import video_id
    from .admin_views import state_of
    if len(text.encode())>1_000_000:raise ImportErrorDetail('CSV exceeds 1 MB.')
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')),strict=True)
    try:
        fields=reader.fieldnames or []
    except csv.Error as exc:
        raise ImportErrorDetail(f'Invalid CSV header: {exc}')
    if len(fields)!=len(set(fields)):raise ImportErrorDetail('Duplicate header names.')
    required={'team_key','title','description','youtube_url'}
    allowed=required|{'project_id','short_description','project_url','demo_youtube_url','repository_url'}
    if not required.issubset(fields) or set(fields)-allowed:
        raise ImportErrorDetail('Headers must include team_key,title,description,youtube_url; optional project_id,short_description,project_url,repository_url,demo_youtube_url.')
    rows=[];errors=[];seen=set()
    try:
        for number,row in enumerate(reader,2):
            if number>1001:raise ImportErrorDetail('CSV exceeds 1000 rows.')
            try:
                if None in row or any(v is None for v in row.values()):raise ValueError('Wrong number of columns.')
                row={k:v.strip() for k,v in row.items()}
                team=Team.objects.filter(name=row['team_key']).first()
                if not team:raise ValueError('Unknown team_key; roster is never changed.')
                if team.pk in seen:raise ValueError('Duplicate team in this import.')
                seen.add(team.pk)
                if not row['title'] or len(row['title'])>200:raise ValueError('Title must contain 1–200 characters.')
                if not row['description']:raise ValueError('Description is required.')
                if len(row.get('short_description',''))>500:raise ValueError('Short description exceeds 500 characters.')
                url=row.get('project_url','')
                if url:
                    try:URLValidator(schemes=['https'])(url)
                    except ValidationError:raise ValueError('Project URL must be a valid HTTPS URL.')
                    if len(url)>200:raise ValueError('Project URL exceeds 200 characters.')
                repository=row.get('repository_url','')
                if repository:
                    try:URLValidator(schemes=['https'])(repository)
                    except ValidationError:raise ValueError('Repository URL must be a valid HTTPS URL.')
                    if len(repository)>200:raise ValueError('Repository URL exceeds 200 characters.')
                video=video_id(row['youtube_url']) if row['youtube_url'] else ''
                project=None;details=None
                supplied=row.get('project_id','')
                if supplied:
                    if not supplied.isdecimal():raise ValueError('project_id must be a website-assigned numeric ID; leave blank for new projects.')
                    project=Project.objects.filter(pk=int(supplied),event=event,team=team).first()
                    if not project:raise ValueError('project_id does not match this event and team.')
                    details=ProjectDetails.objects.filter(project=project).first()
                elif Project.objects.filter(event=event,team=team).exists():
                    raise ValueError('Existing project requires explicit project_id to preview an update.')
                values={'title':row['title'],'description':row['description'],'video':video}
                if 'demo_youtube_url' in fields:values['demo_video']=video_id(row['demo_youtube_url']) if row['demo_youtube_url'] else ''
                if 'short_description' in fields:values['short_description']=row['short_description']
                if 'project_url' in fields:values['project_url']=url
                if 'repository_url' in fields:values['repository_url']=repository
                if project:
                    from .content_policy import ensure_editable
                    ensure_editable(project,values)
                previous=state_of(project,details) if project else None
                changes=[]
                for key,value in values.items():
                    old=(getattr(details,key) if details else '') if key in ('project_url','repository_url') else getattr(project,key,'')
                    if old!=value:changes.append({'field':key,'before':old,'after':value})
                rows.append({'line':number,'team_id':team.pk,'team_name':team.name,'project_id':project.pk if project else None,
                             'values':values,'previous':previous,'changes':changes,'operation':'Update' if project else 'Create'})
            except ValueError as exc:errors.append(f'Row {number}: {exc}')
    except csv.Error as exc:errors.append(f'CSV parse error near line {reader.line_num}: {exc}')
    if not rows and not errors:errors.append('CSV has no project rows.')
    return rows,errors

def digest(event,rows):
    from .models import EventConfig
    config=EventConfig.objects.filter(event=event).first()
    return hashlib.sha256(json.dumps({'event':event.pk,'opened':event.opened,'frozen':config.content_frozen if config else False,'rows':rows},sort_keys=True).encode()).hexdigest()

def preview_token(event,rows):
    return signing.dumps({'hash':digest(event,rows)},salt='w13-import')

def confirm(event,rows,token,actor):
    # Caller owns the activity write transaction and has recomputed rows after locking.
    try:
        if signing.loads(token,salt='w13-import',max_age=3600)!={'hash':digest(event,rows)}:raise signing.BadSignature()
    except signing.BadSignature:raise ImportErrorDetail('Preview expired or project data changed. Preview again before confirming.')
    for row in rows:
        p=Project.objects.get(pk=row['project_id'],event=event) if row['project_id'] else Project(event=event,team_id=row['team_id'])
        previous_video=(p.video,p.demo_video)
        values=dict(row['values']);url=values.pop('project_url',None);repository=values.pop('repository_url',None)
        for key,value in values.items():setattr(p,key,value)
        p.save()
        details=ProjectDetails.objects.filter(project=p).first()
        if details or url is not None or repository is not None:
            details=details or ProjectDetails(project=p)
            if url is not None:details.project_url=url
            if repository is not None:details.repository_url=repository
            from .materials import reset_changed_checks
            reset_changed_checks(details, previous_video, (p.video,p.demo_video))
            details.save()
        Audit.objects.create(action='project import',actor=actor,details={'event':event.pk,'project':p.pk,'operation':row['operation'],'before':row['previous'],'changes':row['changes']})
