"""Account transitions with real CSRF enforcement on an isolated fixture copy."""
import os, sqlite3, uuid, re, html, json
from pathlib import Path
source=Path('local_data/simplified-journey-browser.txt').read_text().strip()
db=Path('local_data')/('qa-account-switch-'+uuid.uuid4().hex+'.sqlite3')
with sqlite3.connect(source) as src,sqlite3.connect(db) as dst:src.backup(dst)
os.environ['W13_QA_DB']=str(db.resolve());os.environ['DJANGO_SETTINGS_MODULE']='exhibition_local_settings'
import django;django.setup()
from django.test import Client
from showcase.models import Assignment,Review,Ballot,Project,StaffAccount
from reviews.models import ReviewerIdentity
checks=[]
def ok(value,label):
 assert value,label
 checks.append(label);print('PASS',label)
def token(r,name='csrfmiddlewaretoken'):
 return html.unescape(re.search(r'name="'+name+r'" value="([^"]+)"',r.content.decode()).group(1))
c=Client(enforce_csrf_checks=True)
def login_student(code):
 r=c.get('/w13/login/');return c.post('/w13/login/',{'csrfmiddlewaretoken':token(r),'account':code,'password':'Journey-2026'})
def login_staff(password='Journey-Staff-2026'):
 r=c.get('/w13/manage/');return c.post('/w13/manage/',{'csrfmiddlewaretoken':token(r),'username':'journey-staff','password':password})
a=ReviewerIdentity.objects.get(code='R-CLEAN-1');b=ReviewerIdentity.objects.get(code='R-CLEAN-2')
ok(login_student(a.code).status_code==302,'student A login with CSRF')
assignment=Assignment.objects.filter(reviewer=a,active=True).first();url=f'/w13/reviews/{assignment.pk}/'
r=c.get(url);oldcsrf=token(r);review={'csrfmiddlewaretoken':oldcsrf,'revision':token(r,'revision'),'strength':'A original','improvement':'More examples',**{f'score{i}':1 for i in range(5)}}
v=c.get('/w13/vote/');ballot={'csrfmiddlewaretoken':token(v),'revision':token(v,'revision'),'choices':[assignment.project_id],'event':1}
marker=c.get('/w13/session-state/').json()['marker']
ok(login_staff('wrong').status_code==200 and c.session.get('w13_identity')==a.pk,'failed Staff login preserves student')
ok(login_staff().status_code==302 and 'w13_identity' not in c.session,'Staff login removes student identity')
ok(c.get('/w13/session-state/').json()['marker']!=marker,'session marker changes on role switch')
for endpoint in ['/w13/','/w13/reviews/',url,'/w13/vote/','/w13/exhibition/']:
 ok(c.get(endpoint).status_code==302,'Staff cannot inherit student page '+endpoint)
ok(c.post(url,review).status_code==403 and not Review.objects.exists(),'old student review CSRF rejected after Staff login')
manage=c.get('/w13/manage/');staffcsrf=token(manage)
ok(b'Student logout' not in manage.content and b'Staff logout' in manage.content,'Staff navbar has only Staff logout')
ok(login_student('wrong').status_code==200 and c.session.get('w13_staff'),'failed student login preserves Staff')
ok(login_student(b.code).status_code==302 and 'w13_staff' not in c.session,'student B login removes Staff identity')
for endpoint in ['/w13/manage/export/','/w13/manage/audit/','/w13/manage/project/1/edit/']:
 ok(c.get(endpoint).status_code==403,'student forbidden Staff endpoint '+endpoint)
ok(c.post('/w13/manage/',{'csrfmiddlewaretoken':staffcsrf,'action':'close','event':1}).status_code==403,'old Staff form cannot close activity after switch')
ok(c.get(url).status_code==404,'student B cannot access A assigned review')
# B current CSRF still cannot make A revision become a B ballot.
ballot['csrfmiddlewaretoken']=token(c.get('/w13/vote/'))
ok(c.post('/w13/vote/',ballot).status_code==409 and not Ballot.objects.exists(),'A ballot revision cannot write to B account')
ok(login_student(a.code).status_code==302,'switch back to student A')
review['csrfmiddlewaretoken']=token(c.get(url));ok(c.post(url,review).status_code==302,'student A can save current review')
ballot['csrfmiddlewaretoken']=token(c.get('/w13/vote/'));ok(c.post('/w13/vote/',ballot).status_code==302,'student A can save own ballot')
ok(login_staff().status_code==302,'switch to Staff again')
r=c.get('/w13/manage/');ok(c.post('/w13/manage/logout/',{'csrfmiddlewaretoken':token(r)}).status_code==302 and not c.session.get('w13_identity') and not c.session.get('w13_staff'),'Staff logout never restores previous student')
ok(login_student(a.code).status_code==302 and Review.objects.filter(assignment=assignment).count()==1 and Ballot.objects.filter(reviewer=a).count()==1,'saved reviews and ballot survive role changes')
r=c.get('/w13/');ok('no-store' in r.headers['Cache-Control'] and b'session-state/' in r.content,'private page disables cache and checks active session')
# Simulate a legacy dual-role session and verify automatic repair.
from showcase.authentication import signature
staff=StaffAccount.objects.get(username='journey-staff');session=c.session;session['w13_staff']=staff.pk;session['w13_staff_signature']=signature(staff);session.save()
ok(c.get('/w13/reviews/').status_code==302 and not c.session.get('w13_identity'),'legacy dual-role session normalizes to Staff')

r=c.get('/w13/exhibition/project/1/')
ok(r.status_code==401 and r.headers.get('X-Frame-Options')=='SAMEORIGIN' and b'Student sign in' in r.content,'expired or Staff iframe shows recovery instead of blocked login redirect')

Path('local_data/account-switching-report.json').write_text(json.dumps({'checks':checks,'database':str(db.resolve())},indent=2))
