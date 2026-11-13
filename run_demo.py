"""Create a fresh local demonstration database and serve it on loopback."""
import argparse
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8084)
    parser.add_argument('--seed-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    data_dir = ROOT / 'local_data'
    data_dir.mkdir(exist_ok=True)
    database = data_dir / f'qa-demo-{uuid4().hex}.sqlite3'
    os.environ['W13_QA_DB'] = str(database)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'exhibition_local_settings'
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import transaction
    from django.utils import timezone
    from reviews.models import ReviewerIdentity, Student, Team
    from showcase.assignment_plans import confirm, preview
    from showcase.models import Event, EventConfig, Project, StaffAccount
    from showcase.views import video_id

    call_command('migrate', verbosity=0)
    now = timezone.now()
    projects = json.loads((ROOT / 'demo/projects.json').read_text(encoding='utf-8'))
    with transaction.atomic():
        event = Event.objects.create(title='AILT9019 Project Exhibition', opened=True, deadline=now + timedelta(days=7))
        EventConfig.objects.create(event=event, confirmed=True, review_start=now,
                                   review_end=event.deadline, vote_start=now, vote_end=event.deadline)
        for number, row in enumerate(projects, 1):
            team = Team.objects.create(name=row['team_name'])
            project = Project.objects.create(
                event=event, team=team, title=row['title'], description=row['description'],
                short_description=row['short_description'], video=video_id(row['presentation_url']),
                demo_video=video_id(row['demo_url']), published=True)
            if project.number != number:
                raise ValueError('Unexpected project numbering')
            student = Student.objects.create(team=team, student_id='123456' if number == 2 else f'DEMO-{number:02d}',
                                             name=f'Demo student {number:02d}')
            student.set_login_password('123456')
            ReviewerIdentity.objects.create(student=student, code=f'R-DEMO-{number:02d}')
        staff = StaffAccount(username='654321')
        staff.set_password('654321')
        staff.save()
        plan = preview(event)
        confirm(event, plan['token'], 'demo seed')

    print(f'Demo database: {database}', flush=True)
    if not args.seed_only:
        from wsgiref.simple_server import make_server
        from rehearsal_wsgi import application
        print(f'Course: http://127.0.0.1:{args.port}/review-system/w13/course/', flush=True)
        with make_server('127.0.0.1', args.port, application) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
