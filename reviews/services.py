import hashlib
import random
import secrets
import statistics
import time

from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import (
    CRITERIA,
    CourseStaff,
    Proposal,
    ReviewAssignment,
    ReviewEvent,
    ReviewerIdentity,
    Student,
)

PROPOSAL_EVENT_SLUG = "w5-proposal"


def get_or_create_proposal_event() -> ReviewEvent:
    event, _ = ReviewEvent.objects.get_or_create(
        slug=PROPOSAL_EVENT_SLUG,
        defaults={
            "title": "W5 Proposal review",
            "kind": ReviewEvent.KIND_PROPOSAL,
            "description": "Anonymous review of another group's project proposal.",
            "is_open": True,
        },
    )
    return event


def open_events():
    events = list(ReviewEvent.objects.filter(is_open=True))
    if events:
        return events
    return [get_or_create_proposal_event()]

ID_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
OTP_TTL_SECONDS = 10 * 60
HKU_EMAIL_SUFFIX = ".hku.hk"


def generate_login_password() -> str:
    """Readable issued password. Students cannot change it in the app."""
    body = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
    return f"{body[:4]}-{body[4:]}"


def generate_reviewer_code(existing: set[str] | None = None) -> str:
    existing = existing or set()
    while True:
        body = "".join(secrets.choice(ID_ALPHABET) for _ in range(4))
        code = f"R-{body}"
        if code not in existing:
            return code


def assign_reviews(reviewers, proposals, per_student=1):
    """Give each reviewer `per_student` proposals from other teams. Balance load."""
    load = {proposal.pk: 0 for proposal in proposals}
    created = []
    reviewers = list(reviewers)
    random.shuffle(reviewers)
    for reviewer in reviewers:
        own_team_id = reviewer.student.team_id
        eligible = [p for p in proposals if p.team_id != own_team_id]
        random.shuffle(eligible)
        eligible.sort(key=lambda p: load[p.pk])
        chosen = eligible[:per_student]
        for proposal in chosen:
            created.append((reviewer, proposal))
            load[proposal.pk] += 1
    return created


def is_hku_email(email: str) -> bool:
    value = email.lower()
    return value.endswith("@hku.hk") or value.endswith(HKU_EMAIL_SUFFIX)


def make_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def store_otp(session, *, email: str, purpose: str, extra: dict) -> str:
    code = make_otp()
    session["email_otp"] = {
        "hash": hash_otp(code),
        "email": email.lower(),
        "purpose": purpose,
        "extra": extra,
        "expires": int(time.time()) + OTP_TTL_SECONDS,
    }
    session.modified = True
    dispatch_otp(email, code, purpose)
    return code


def dispatch_otp(email: str, code: str, purpose: str) -> Path:
    """Write the one-time code to a local outbox. SMTP is not configured yet."""
    outbox = Path(settings.BASE_DIR) / "var" / "otp_outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    body = (
        f"to: {email.lower()}\n"
        f"purpose: {purpose}\n"
        f"code: {code}\n"
        f"sent_at: {timezone.now().isoformat(timespec='seconds')}\n"
    )
    path = outbox / f"{stamp}-{purpose}.txt"
    path.write_text(body, encoding="utf-8")
    (outbox / "latest.txt").write_text(body, encoding="utf-8")
    return path


def verify_otp(session, *, email: str, purpose: str, code: str) -> dict | None:
    payload = session.get("email_otp") or {}
    if not payload:
        return None
    if payload.get("purpose") != purpose:
        return None
    if payload.get("email") != email.lower():
        return None
    if int(payload.get("expires") or 0) < int(time.time()):
        return None
    if payload.get("hash") != hash_otp(code.strip()):
        return None
    session.pop("email_otp", None)
    return payload.get("extra") or {}


def student_email_taken(email: str, exclude_pk=None) -> bool:
    qs = Student.objects.filter(email__iexact=email)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def staff_email_taken(email: str, exclude_pk=None) -> bool:
    qs = CourseStaff.objects.filter(email__iexact=email, registered=True)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def check_student_register(uid: str, email: str) -> tuple[Student | None, str]:
    """Register only if UID is on the imported list and the email matches that row."""
    email = email.lower()
    if not is_hku_email(email):
        return None, "Use an HKU email (must end with hku.hk)."
    student = Student.objects.filter(student_id=uid).first()
    if student is None:
        return None, "This UID is not on the course list."
    if not student.email:
        return None, "This UID has no roster email. Ask staff to import the student list."
    if student.email.lower() != email:
        return None, "Use the same HKU email as on the course / Moodle list."
    identity = ReviewerIdentity.objects.filter(student=student).first()
    if identity is not None and identity.is_activated:
        return None, "This UID is already registered. Log in instead."
    return student, ""


def check_staff_register(uid: str, email: str) -> tuple[CourseStaff | None, str]:
    email = email.lower()
    if not is_hku_email(email):
        return None, "Use an HKU email (must end with hku.hk)."
    staff = CourseStaff.objects.filter(uid=uid).first()
    if staff is None:
        return None, "This UID is not on the course-staff list."
    if staff.registered:
        return None, "This staff UID already has an account. Log in instead."
    if staff_email_taken(email, exclude_pk=staff.pk):
        return None, "This email is already registered to another staff account."
    return staff, ""


def find_student_identity(token: str) -> tuple[ReviewerIdentity | None, str]:
    token = token.strip()
    if token.upper().startswith("R-"):
        identity = (
            ReviewerIdentity.objects.select_related("student")
            .filter(code=token.upper())
            .first()
        )
        if identity is None:
            return None, "Unknown Reviewer ID."
        return identity, ""
    student = Student.objects.filter(student_id=token).first()
    if student is None:
        return None, "Unknown UID."
    identity = ReviewerIdentity.objects.select_related("student").filter(student=student).first()
    if identity is None:
        return None, "This UID has no Reviewer ID yet. Ask the course team."
    return identity, ""


def authenticate_student(account: str, password: str) -> tuple[ReviewerIdentity | None, str]:
    identity, error = find_student_identity(account)
    if identity is None:
        return None, "Wrong account or password."
    if not identity.student.check_login_password(password):
        return None, "Wrong account or password."
    return identity, ""


def find_staff_account(token: str) -> tuple[CourseStaff | None, str]:
    token = token.strip()
    staff = CourseStaff.objects.filter(uid=token).first()
    if staff is None:
        staff = CourseStaff.objects.filter(email__iexact=token).first()
    if staff is None:
        return None, "Unknown staff UID."
    if not staff.registered or not staff.email:
        return None, "This staff UID has not finished registration."
    return staff, ""


def claim_reviewer(student, email: str | None = None) -> ReviewerIdentity:
    return activate_reviewer(student, email=email)


def activate_reviewer(student, email: str | None = None) -> ReviewerIdentity:
    if email and (not student.email or student.email.lower() != email.lower()):
        student.email = email.lower()
        student.save(update_fields=["email"])
    identity = ReviewerIdentity.objects.filter(student=student).first()
    if identity is None:
        codes = set(ReviewerIdentity.objects.values_list("code", flat=True))
        identity = ReviewerIdentity.objects.create(
            student=student,
            code=generate_reviewer_code(codes),
            activated_at=None,
        )
    now = timezone.now()
    if identity.activated_at is None:
        identity.activated_at = now
    identity.last_login_at = now
    identity.save(update_fields=["activated_at", "last_login_at"])
    if not identity.assignments.exists():
        proposals = list(Proposal.objects.select_related("team"))
        pairs = assign_reviews([identity], proposals, per_student=1)
        ReviewAssignment.objects.bulk_create(
            [
                ReviewAssignment(
                    event=proposal.event,
                    reviewer=reviewer,
                    proposal=proposal,
                )
                for reviewer, proposal in pairs
            ]
        )
    return identity


def mark_reviewer_login(identity: ReviewerIdentity) -> None:
    now = timezone.now()
    identity.last_login_at = now
    fields = ["last_login_at"]
    if identity.activated_at is None:
        identity.activated_at = now
        fields.append("activated_at")
    identity.save(update_fields=fields)


def register_staff(staff: CourseStaff, email: str) -> CourseStaff:
    staff.email = email.lower()
    staff.registered = True
    staff.save(update_fields=["email", "registered"])
    return staff


def can_view_proposal(reviewer, proposal) -> bool:
    if proposal.team_id == reviewer.student.team_id:
        return True
    return ReviewAssignment.objects.filter(
        reviewer=reviewer, proposal=proposal
    ).exists()


# A review is flagged when its total is at least this far from the
# median of currently counted reviews on the same proposal.
ANOMALY_ABS_THRESHOLD = 12
ANOMALY_MIN_N = 3


def detect_anomalies(reviews) -> dict:
    """Return {review.pk: bool} for submitted reviews on one proposal."""
    flags = {review.pk: False for review in reviews}
    counted = [review for review in reviews if review.counted]
    if len(counted) < ANOMALY_MIN_N:
        return flags
    median = statistics.median(review.total for review in counted)
    for review in counted:
        if abs(review.total - median) >= ANOMALY_ABS_THRESHOLD:
            flags[review.pk] = True
    return flags


def _score_summary(values) -> dict:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": round(statistics.mean(values), 2),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def proposal_review_stats(reviews) -> dict:
    flagged = detect_anomalies(reviews)
    counted = [review for review in reviews if review.counted]
    totals = [review.total for review in counted]
    parts = {}
    for name, _label, _maximum, _part in CRITERIA:
        parts[name] = _score_summary([getattr(review, name) for review in counted])
    summary = _score_summary(totals)
    return {
        "n": len(reviews),
        "n_counted": len(counted),
        "n_excluded": sum(1 for review in reviews if not review.counted),
        "n_flagged": sum(1 for value in flagged.values() if value),
        "mean": summary["mean"],
        "median": summary["median"],
        "min": summary["min"],
        "max": summary["max"],
        "content": _score_summary([review.content_total for review in counted]),
        "delivery": _score_summary([review.delivery_total for review in counted]),
        "parts": parts,
        "flagged": flagged,
    }
