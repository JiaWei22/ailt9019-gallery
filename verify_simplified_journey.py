"""Current Moodle-to-gallery journey, isolated DB; real HTTP views and cross-page state."""
import os,uuid,re,html,csv,io,sqlite3,json
from pathlib import Path
from datetime import timedelta
uid=uuid.uuid4().hex;db=Path('local_data')/f'qa-simplified-{uid}.sqlite3'
os.environ['W13_QA_DB']=str(db.resolve());os.environ['DJANGO_SETTINGS_MODULE']='exhibition_local_settings'
import django;django.setup()
from django.core.management import call_command
from django.test import Client
from django.test.utils import setup_test_environment
from django.utils import timezone
from reviews.models import Team,Student,ReviewerIdentity
from showcase.models import Event,EventConfig,Project,Assignment,Review,Ballot,StaffAccount,ProjectDetails
from showcase.reporting import progress,vote_totals
setup_test_environment();call_command('migrate',verbosity=0)
checks=[]
def ok(condition,label):
 assert condition,label
 checks.append(label);print('PASS',label)
def token(response,name='preview_token'):
 m=re.search(r'name="'+name+r'" value="([^"]+)"',response.content.decode());assert m,(name,response.status_code,response.content[:150]);return html.unescape(m.group(1))
now=timezone.now();e=Event.objects.create(title='AILT9019 Journey QA',opened=True,deadline=now+timedelta(days=3))
cfg=EventConfig.objects.create(event=e,confirmed=True,allow_self_vote=True,allow_vote_edit=True,allow_review_edit=True,review_start=now-timedelta(days=1),review_end=e.deadline,vote_start=now-timedelta(days=1),vote_end=e.deadline)
people=[]
for n in range(6):
 team=Team.objects.create(name=f'Journey team {n+1}');student=Student.objects.create(student_id=f'JOURNEY-{n+1}',name='QA student',team=team);student.set_login_password('Journey-2026');people.append(ReviewerIdentity.objects.create(student=student,code=f'R-CLEAN-{n+1}'))
admin=StaffAccount(username='journey-staff');admin.set_password('Journey-Staff-2026');admin.save()
s=Client();staff=Client();ok(s.get('/w13/reviews/').status_code==302,'anonymous student redirected')
ok(s.post('/w13/login/',{'account':people[0].code,'password':'Journey-2026'}).status_code==302,'student login')
ok(staff.post('/w13/manage/',{'username':'journey-staff','password':'Journey-Staff-2026'}).status_code==302,'staff login')
ok(b'Submit on Moodle' in s.get('/w13/my-project/').content and s.post('/w13/my-project/',{}).status_code==403,'Moodle instructions; student direct publication forbidden')
fields=['team_key','title','description','youtube_url','demo_youtube_url','project_url','repository_url'];out=io.StringIO();w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
for n,i in enumerate(people):w.writerow(dict(team_key=i.student.team.name,title=f'Journey project {n+1}',description='Two-video workflow check',youtube_url='https://youtu.be/aqz-KE-bpKQ',demo_youtube_url='https://youtu.be/M7lc1UVf-VE',project_url='https://example.com/project',repository_url='https://github.com/IILKA/ailit9019-review-sys'))
body={'event':e.pk,'action':'import','csv':out.getvalue()};r=staff.post('/w13/manage/',body);ok(r.status_code==200 and Project.objects.count()==0,'CSV preview has no writes')
r=staff.post('/w13/manage/',dict(body,confirm='1',preview_token=token(r)));ok(r.status_code==302 and Project.objects.count()==6 and not Project.objects.filter(published=True).exists(),'staff imports six draft projects')
ps=list(Project.objects.order_by('pk'));ok(all(p.video and p.demo_video and p.projectdetails.repository_url for p in ps),'both videos and repository survive import')
def publish(p):
 body={'event':e.pk,'action':'publish','project':p.pk};r=staff.post('/w13/manage/',body);return staff.post('/w13/manage/',dict(body,confirm='1',preview_token=token(r)))
for p in ps:ok(publish(p).status_code==302,f'publish project {p.pk}')
body={'event':e.pk,'action':'assign'};r=staff.post('/w13/manage/',body);ok(Assignment.objects.count()==0,'assignment preview has no writes')
ok(staff.post('/w13/manage/',dict(body,confirm='1',preview_token=token(r))).status_code==302,'staff confirms assignments')
tasks=list(Assignment.objects.filter(reviewer=people[0],active=True));ok(len(tasks)==3 and all(a.project.team_id!=people[0].student.team_id for a in tasks),'three cross-team reviews assigned')
# Separate browser snapshot: ready to execute the student workflow manually.
browser_db=Path('local_data')/f'qa-simplified-browser-{uid}.sqlite3'
with sqlite3.connect(db) as src,sqlite3.connect(browser_db) as dest:src.backup(dest)
Path('local_data/simplified-journey-browser.txt').write_text(str(browser_db.resolve()))
for k,a in enumerate(tasks,1):
 url=f'/w13/reviews/{a.pk}/';r=s.get(url);ok(r.status_code==200 and all(x in r.content for x in [b'Presentation video',b'Demo video',b'name="score0"']),'dual videos and scoring together')
 body={'revision':token(r,'revision'),'strength':'Clear evidence','improvement':'Add more failure examples',**{f'score{j}':1 for j in range(5)}};ok(s.post(url,body).status_code==302,f'save review {k}')
 home=s.get('/w13/');taskpage=s.get('/w13/reviews/');ok(home.context['todo']['completed']==k and taskpage.context['completed']==k,f'student pages agree at {k}/3')
 item=next(x for x in progress(e) if x['reviewer']==people[0].code);ok(item['completed']==k,f'staff progress agrees at {k}/3')
ok(b'View your reviews' in s.get('/w13/').content,'completed review action changes to View your reviews')
r=staff.get(f'/w13/manage/event/{e.pk}/edit/');form=r.context['form'];ok('submissions_enabled' not in form.fields and 'submission_deadline' not in form.fields,'obsolete Gallery submission controls absent')
body={}
for name in form.fields:
 value=form[name].value()
 if value is None:continue
 if isinstance(value,bool):
  if value:body[name]='on'
 else:body[name]=value
ok(staff.post(f'/w13/manage/event/{e.pk}/edit/',body).status_code==302,'current event configuration still saves')
old=token(s.get('/w13/vote/'),'revision');body={'event':e.pk,'choices':[tasks[0].project_id],'revision':old};r=s.post('/w13/vote/preview/',body);ok(r.status_code==200 and not Ballot.objects.exists(),'vote preview does not save')
ok(s.post('/w13/vote/',body).status_code==302,'save ballot');ok(s.get('/w13/').context['todo']['valid_votes']==1,'homepage shows one valid vote')
ok(s.post('/w13/vote/',body).status_code==409,'old page cannot overwrite ballot')
# Withdrawal archives an already-completed review and removes its vote from totals.
withdrawn=tasks[0].project;ok(publish(withdrawn).status_code==302,'withdraw project after review/vote')
ok(s.get('/w13/').context['todo']['completed']==2 and s.get('/w13/reviews/').context['completed']==2,'withdrawal updates student completion to 2/3')
r=staff.get('/w13/manage/');ok(b'<strong>2</strong> / 3' in r.content and b'replacement needed' in r.content,'staff also shows 2/3 and missing assignment after withdrawal')
ok(s.get('/w13/').context['todo']['valid_votes']==0,'withdrawn project vote excluded')
ok(s.get(f'/w13/projects/{withdrawn.pk}/').status_code==404,'withdrawn project hidden')
r=s.get(f'/w13/reviews/{tasks[0].pk}/');ok(b'Archived' in r.content and b'<textarea' not in r.content,'withdrawn review stays read-only')
body={'event':e.pk,'action':'assign'};r=staff.post('/w13/manage/',body);ok(staff.post('/w13/manage/',dict(body,confirm='1',preview_token=token(r))).status_code==302,'replacement assignment confirmed')
a=Assignment.objects.filter(reviewer=people[0],active=True,review__isnull=True).get();url=f'/w13/reviews/{a.pk}/';r=s.get(url);body={'revision':token(r,'revision'),'strength':'Replacement review','improvement':'Test edge cases',**{f'score{j}':1 for j in range(5)}};ok(s.post(url,body).status_code==302,'replacement review saved');ok(s.get('/w13/').context['todo']['completed']==3,'replacement restores 3/3')
ok(publish(withdrawn).status_code==302 and s.get('/w13/').context['todo']['valid_votes']==0,'republish does not silently restore old vote')
r=staff.get('/w13/manage/export/',{'event':e.pk,'kind':'reviews'});rows=list(csv.DictReader(io.StringIO(r.content.decode())));ok(sum(x['counts_toward_completion']=='True' for x in rows if x['reviewer_id']==people[0].code)==3,'export counts exactly three current reviews; archived review excluded')
old_count=Review.objects.count();old_votes=list(Ballot.objects.values_list('choices',flat=True));ok(staff.post('/w13/manage/',{'event':e.pk,'action':'close'}).status_code==302,'staff closes event');ok(b'id="ballot-form"' not in s.get('/w13/vote/').content,'closed voting has no editable ballot')
s.post('/w13/vote/',{'event':e.pk,'choices':[ps[1].pk]});s.post(url,body);ok(Review.objects.count()==old_count and list(Ballot.objects.values_list('choices',flat=True))==old_votes,'closed activity rejects writes')
for page in ['/w13/','/w13/reviews/','/w13/vote/','/w13/manage/','/w13/exhibition/']:
 c=staff if 'manage' in page else s;r=c.get(page);ok(r.status_code==200 and b'Choose activity' not in r.content and b'LOCAL DEMO' not in r.content,'simplified page renders: '+page)
Path('local_data/simplified-journey-report.json').write_text(json.dumps({'passed':True,'checks':checks,'database':str(db.resolve()),'browser_database':str(browser_db.resolve())},indent=2));print('BROWSER_DB',browser_db.resolve())
