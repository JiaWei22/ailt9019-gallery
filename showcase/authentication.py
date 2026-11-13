"""W13 identities and shared throttling, without writes to W5/auth user records."""
from datetime import timedelta
from django.conf import settings
from django.middleware.csrf import rotate_token
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac,constant_time_compare
from .models import StaffAccount,LoginBucket

STAFF_KEY='w13_staff'

def staff_identity(request):
    staff=StaffAccount.objects.filter(pk=request.session.get(STAFF_KEY),enabled=True).first()
    if staff and constant_time_compare(request.session.get('w13_staff_signature',''), signature(staff)):
        # Normalize older sessions that held both Gallery roles.
        request.session.pop('w13_identity', None)
        return staff
    return None

def signature(staff):
    return salted_hmac('w13-staff-session',staff.password_hash).hexdigest()

def sign_in(request,staff):
    request.session.cycle_key()
    rotate_token(request)
    request.session.pop('w13_identity', None)
    request.session[STAFF_KEY]=staff.pk
    request.session['w13_staff_signature']=signature(staff)

def permitted_attempt(request,role,account):
    """Fixed one-minute account/address windows, shared across sessions and processes.

    Update is the first operation in each transaction to acquire SQLite's write
    lock before reading a counter. No reliance on select_for_update on SQLite.
    REMOTE_ADDR is used as-is; forwarded headers are not trusted.
    """
    now=timezone.now()
    limits=[('account',account.strip().casefold(),getattr(settings,'W13_ACCOUNT_LOGIN_LIMIT',8)),
            ('address',request.META.get('REMOTE_ADDR','unknown'),getattr(settings,'W13_ADDRESS_LOGIN_LIMIT',1000))]
    allowed=True
    with transaction.atomic():
        for kind,value,limit in limits:
            key=salted_hmac('w13-login-bucket',role+':'+kind+':'+value,algorithm='sha256').hexdigest()
            changed=LoginBucket.objects.filter(key=key).update(attempts=F('attempts')+1)
            if not changed:
                bucket=LoginBucket.objects.create(key=key,attempts=1,expires=now+timedelta(seconds=60))
            else:
                bucket=LoginBucket.objects.get(key=key)
                if bucket.expires<=now:
                    bucket.attempts=1;bucket.expires=now+timedelta(seconds=60)
                    bucket.save(update_fields=['attempts','expires'])
            allowed=allowed and bucket.attempts<=limit
    return allowed


def session_marker(request):
    """Opaque UI marker; never exposes the session key or credentials."""
    staff = staff_identity(request)
    role = f'staff:{staff.pk}' if staff else f"student:{request.session.get('w13_identity', '')}"
    return salted_hmac('w13-ui-session', role + ':' + (request.session.session_key or '')).hexdigest()
