from getpass import getpass
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from showcase.models import StaffAccount,Audit

class Command(BaseCommand):
    help='Create a new W13-only staff account; refuses to overwrite existing accounts.'

    def add_arguments(self,parser):
        parser.add_argument('username')

    def handle(self,*args,**options):
        username=options['username'].strip()
        if not username or len(username)>80:
            raise CommandError('Username must contain 1–80 characters.')
        if StaffAccount.objects.filter(username=username).exists():
            raise CommandError('Account already exists; no changes made.')
        password=getpass('New W13 password (not echoed): ')
        if len(password)<12:
            raise CommandError('Use at least 12 characters.')
        if password!=getpass('Repeat password: '):
            raise CommandError('Passwords do not match.')
        try:validate_password(password)
        except ValidationError as exc:raise CommandError('; '.join(exc.messages))
        with transaction.atomic():
            account=StaffAccount(username=username)
            account.set_password(password);account.save(force_insert=True)
            Audit.objects.create(action='staff created',actor='management command',details={'staff':account.pk})
        self.stdout.write(self.style.SUCCESS('W13 staff account created.'))
