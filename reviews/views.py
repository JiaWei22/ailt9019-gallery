import csv
import os
import time
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .backup import backup_if_stale, create_backup, latest_backup
from .forms import (
    AddStudentForm,
    ChangeGroupForm,
    ChangePasswordForm,
    OtpForm,
    ReviewForm,
    RosterImportForm,
    StaffPasswordForm,
    StudentLoginForm,
)
from .models import (
    CRITERIA,
    Proposal,
    Review,
    ReviewAssignment,
    ReviewEvent,
    ReviewerIdentity,
    Student,
    Team,
)
from .preview import render_pdf_pages
from .services import (
    authenticate_student,
    can_view_proposal,
    get_or_create_proposal_event,
    mark_reviewer_login,
    proposal_review_stats,
    store_otp,
    verify_otp,
)
from .submissions_upload import (
    apply_pdf_uploads,
    collect_pdf_uploads,
    match_pdfs_to_roster,
    pdf_library_rows,
    replace_group_pdf,
    submission_status_by_team,
)
from .roster import (
    RosterError,
    add_student,
    assign_event_reviews,
    review_assignment_preview,
    change_student_group,
    credentials_csv_bytes,
    delete_student,
    existing_group_names,
    import_roster,
    issue_missing_ids,
    parse_roster_file,
    preview_roster_import,
    reset_student_password,
    roster_rows,
    roster_summary,
    template_csv_bytes,
)


def _current_reviewer(request):
    pk = request.session.get(settings.SESSION_REVIEWER_KEY)
    if not pk:
        return None
    return ReviewerIdentity.objects.filter(pk=pk).select_related("student", "student__team").first()


def _require_reviewer(request):
    reviewer = _current_reviewer(request)
    if reviewer is None:
        return None, redirect("reviewer_login")
    return reviewer, None


def _require_staff(request):
    if not request.session.get(settings.SESSION_STAFF_KEY):
        return redirect("staff_login")
    return None


def _import_lock_path() -> Path:
    return Path(settings.BASE_DIR) / "var" / "roster_import.lock"


def _acquire_import_lock():
    path = _import_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and time.time() - path.stat().st_mtime > 600:
        path.unlink(missing_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None


def _release_import_lock(handle) -> None:
    if handle is None:
        return
    os.close(handle)
    _import_lock_path().unlink(missing_ok=True)


def _redirect_roster(request, *, student=None, note="", level="success"):
    if student is not None:
        request.session["roster_focus_id"] = student.pk
        request.session["roster_focus_note"] = note
        request.session["roster_focus_level"] = level
        return redirect(f"{reverse('staff_dashboard')}#student-{student.pk}")
    request.session.pop("roster_focus_id", None)
    request.session.pop("roster_focus_note", None)
    request.session.pop("roster_focus_level", None)
    if note:
        getattr(messages, level)(request, note)
    return redirect("staff_dashboard")


def _assignment_for(reviewer, proposal):
    return ReviewAssignment.objects.filter(reviewer=reviewer, proposal=proposal).first()


def _review_of(assignment):
    if assignment is None:
        return None
    return Review.objects.filter(assignment=assignment).first()


def home(request):
    if request.session.get(settings.SESSION_STAFF_KEY):
        return redirect("staff_events")
    if _current_reviewer(request):
        return redirect("event_list")
    return redirect("reviewer_login")


def _assignment_event_buckets(reviewer, event=None):
    assignments = (
        ReviewAssignment.objects.filter(reviewer=reviewer)
        .select_related("event", "proposal", "proposal__team")
        .order_by("event__pk", "pk")
    )
    if event is not None:
        assignments = assignments.filter(event=event)
    grouped = {}
    for assignment in assignments:
        bucket = grouped.setdefault(
            assignment.event_id, {"event": assignment.event, "rows": []}
        )
        bucket["rows"].append(
            {
                "assignment": assignment,
                "submitted": _review_of(assignment) is not None,
            }
        )
    events = []
    for bucket in grouped.values():
        bucket["total"] = len(bucket["rows"])
        bucket["done"] = sum(1 for row in bucket["rows"] if row["submitted"])
        events.append(bucket)
    return events, assignments.count()


def reviewer_register(request):
    return redirect("reviewer_login")


def claim_success(request):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    return render(request, "reviews/claim_success.html", {"reviewer_code": reviewer.code})


@require_http_methods(["GET", "POST"])
def reviewer_login(request):
    if _current_reviewer(request):
        return redirect("event_list")
    form = StudentLoginForm(request.POST or None)
    error = ""
    if request.method == "POST" and form.is_valid():
        identity, error = authenticate_student(
            form.cleaned_data["account"],
            form.cleaned_data["password"],
        )
        if identity:
            mark_reviewer_login(identity)
            request.session[settings.SESSION_REVIEWER_KEY] = identity.pk
            return redirect("event_list")
    return render(
        request,
        "reviews/login.html",
        {"form": form, "error": error},
    )


def reviewer_logout(request):
    request.session.pop(settings.SESSION_REVIEWER_KEY, None)
    request.session.pop("email_otp", None)
    return redirect("reviewer_login")


def event_list(request):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    events, total = _assignment_event_buckets(reviewer)
    for bucket in events:
        bucket["href"] = reverse("event_detail", args=[bucket["event"].slug])
        bucket["meta"] = f"{bucket['done']} / {bucket['total']} assigned reviews submitted"
    return render(
        request,
        "reviews/event_choose.html",
        {
            "choose_title": "Review events",
            "choose_lede": "Choose an event first. Assigned work, your reviews, and team feedback all sit under that event.",
            "events": events,
            "total": total,
        },
    )


def _can_open_event(reviewer, event) -> bool:
    if reviewer.assignments.filter(event=event).exists():
        return True
    return Proposal.objects.filter(event=event, team=reviewer.student.team).exists()


def event_detail(request, event_slug):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    event = get_object_or_404(ReviewEvent, slug=event_slug)
    if not _can_open_event(reviewer, event):
        raise Http404
    events, total = _assignment_event_buckets(reviewer, event=event)
    return render(
        request,
        "reviews/tasks.html",
        {
            "event": event,
            "events": events,
            "total": total,
            "event_section": "assigned",
        },
    )


def task_list(request):
    return redirect("event_list")


def forum(request, proposal_id):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    proposal = get_object_or_404(Proposal.objects.select_related("team", "event"), pk=proposal_id)
    if not can_view_proposal(reviewer, proposal):
        raise Http404
    own_team = proposal.team_id == reviewer.student.team_id
    assignment = _assignment_for(reviewer, proposal)
    incoming = []
    if own_team:
        incoming = list(
            Review.objects.filter(assignment__proposal=proposal)
            .select_related("assignment__reviewer")
            .order_by("submitted_at")
        )
    return render(
        request,
        "reviews/forum.html",
        {
            "proposal": proposal,
            "own_team": own_team,
            "assignment": assignment,
            "incoming": incoming,
            "my_review": _review_of(assignment),
        },
    )


@require_http_methods(["GET", "POST"])
def review_form(request, assignment_id):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("event", "proposal", "proposal__team"),
        pk=assignment_id,
        reviewer=reviewer,
    )
    existing = _review_of(assignment)
    locked = not assignment.event.is_open
    if locked and request.method == "POST":
        messages.error(request, assignment.event.lock_message())
        return redirect("review_form", assignment_id=assignment.pk)
    if locked and existing:
        return render(
            request,
            "reviews/review_readonly.html",
            {
                "assignment": assignment,
                "review": existing,
                "locked": True,
                "lock_message": assignment.event.lock_message(),
            },
        )
    if locked:
        return render(
            request,
            "reviews/review_form.html",
            {
                "assignment": assignment,
                "locked": True,
                "lock_message": assignment.event.lock_message(),
            },
        )
    if not assignment.proposal.file and existing is None:
        return render(
            request,
            "reviews/review_form.html",
            {
                "assignment": assignment,
                "locked": True,
                "lock_message": "The PDF for this submission is not uploaded yet.",
            },
        )
    if existing and not existing.edit_allowed:
        return render(
            request,
            "reviews/review_readonly.html",
            {
                "assignment": assignment,
                "review": existing,
                "locked": False,
            },
        )

    form = ReviewForm(
        request.POST or None,
        initial_review=existing if existing and existing.edit_allowed else None,
    )
    if request.method == "POST" and form.is_valid():
        if existing:
            for field, value in form.cleaned_data.items():
                setattr(existing, field, value)
            existing.edit_allowed = False
            existing.save()
        else:
            Review.objects.create(assignment=assignment, **form.cleaned_data)
        return redirect("event_my_reviews", event_slug=assignment.event.slug)
    return render(
        request,
        "reviews/review_form.html",
        {
            "assignment": assignment,
            "form": form,
            "criterion_rows": form.criterion_rows(),
            "suggestions_field": form["suggestions"],
            "preview_pages": range(1, _preview_page_count(assignment.proposal) + 1),
            "revising": bool(existing),
            "locked": False,
        },
    )


@require_POST
def request_edit(request, assignment_id):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    assignment = get_object_or_404(
        ReviewAssignment, pk=assignment_id, reviewer=reviewer
    )
    review = _review_of(assignment)
    if review is None:
        raise Http404
    if not assignment.event.is_open:
        messages.error(request, assignment.event.lock_message())
        return redirect("review_form", assignment_id=assignment.pk)
    review.edit_allowed = True
    review.edit_requested_at = timezone.now()
    review.save(update_fields=["edit_allowed", "edit_requested_at"])
    return redirect("review_form", assignment_id=assignment.pk)


def proposal_file(request, proposal_id):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    proposal = get_object_or_404(Proposal, pk=proposal_id)
    if not can_view_proposal(reviewer, proposal):
        raise Http404
    if not proposal.file:
        raise Http404
    response = HttpResponse(proposal.file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{proposal.download_name}"'
    return response


def proposal_preview_page(request, assignment_id, page_number):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("proposal"),
        pk=assignment_id,
        reviewer=reviewer,
    )
    pages = _render_preview(assignment.proposal)
    if page_number < 1 or page_number > len(pages):
        raise Http404
    return FileResponse(pages[page_number - 1].open("rb"), content_type="image/png")


def _render_preview(proposal: Proposal):
    if not proposal.file:
        return []
    return render_pdf_pages(Path(proposal.file.path), proposal.file_token)


def _preview_page_count(proposal: Proposal) -> int:
    try:
        return len(_render_preview(proposal))
    except Exception:
        return 0


def my_reviews(request):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    events, total = _assignment_event_buckets(reviewer)
    for bucket in events:
        bucket["href"] = reverse("event_my_reviews", args=[bucket["event"].slug])
        bucket["meta"] = f"{bucket['done']} review(s) submitted in this event"
    return render(
        request,
        "reviews/event_choose.html",
        {
            "choose_title": "Your reviews",
            "choose_lede": "Choose the event first, then open the reviews you submitted in that campaign.",
            "events": events,
            "total": total,
        },
    )


def event_my_reviews(request, event_slug):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    event = get_object_or_404(ReviewEvent, slug=event_slug)
    if not _can_open_event(reviewer, event):
        raise Http404
    reviews = (
        Review.objects.filter(assignment__reviewer=reviewer, assignment__event=event)
        .select_related("assignment__event", "assignment__proposal")
        .order_by("submitted_at")
    )
    return render(
        request,
        "reviews/my_reviews.html",
        {"event": event, "reviews": reviews, "event_section": "mine"},
    )


def incoming_reviews(request):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    events = []
    for proposal in (
        Proposal.objects.filter(team=reviewer.student.team)
        .select_related("event")
        .order_by("event__pk")
    ):
        n = Review.objects.filter(assignment__proposal=proposal).count()
        events.append(
            {
                "event": proposal.event,
                "href": reverse("event_feedback", args=[proposal.event.slug]),
                "meta": f"{n} review(s) of your team proposal",
            }
        )
    return render(
        request,
        "reviews/event_choose.html",
        {
            "choose_title": "Feedback for your team proposal",
            "choose_lede": "Choose the event first, then read the reviews of your team proposal.",
            "events": events,
        },
    )


def event_feedback(request, event_slug):
    reviewer, bounce = _require_reviewer(request)
    if bounce:
        return bounce
    event = get_object_or_404(ReviewEvent, slug=event_slug)
    proposal = get_object_or_404(
        Proposal.objects.select_related("event"),
        team=reviewer.student.team,
        event=event,
    )
    reviews = list(
        Review.objects.filter(assignment__proposal=proposal)
        .select_related("assignment__reviewer")
        .order_by("submitted_at")
    )
    return render(
        request,
        "reviews/incoming.html",
        {
            "event": event,
            "proposal": proposal,
            "reviews": reviews,
            "event_section": "feedback",
        },
    )


def staff_register(request):
    return redirect("staff_login")


@require_http_methods(["GET", "POST"])
def staff_login(request):
    if request.session.get(settings.SESSION_STAFF_KEY):
        return redirect("staff_dashboard")
    form = StaffPasswordForm(request.POST or None)
    error = ""
    if request.method == "POST":
        if form.is_valid() and form.cleaned_data.get("password") == settings.STAFF_PASSWORD:
            request.session[settings.SESSION_STAFF_KEY] = True
            backup_if_stale("staff-login")
            return redirect("staff_dashboard")
        error = "Wrong password."
    return render(
        request,
        "reviews/staff_login.html",
        {"password_form": form, "error": error},
    )


def staff_logout(request):
    request.session.pop(settings.SESSION_STAFF_KEY, None)
    return redirect("staff_login")


def staff_events(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    events = []
    for event in ReviewEvent.objects.all():
        n_submissions = event.submissions.count()
        n_assignments = event.assignments.count()
        n_reviews = Review.objects.filter(assignment__event=event).count()
        events.append(
            {
                "event": event,
                "n_submissions": n_submissions,
                "n_assignments": n_assignments,
                "n_reviews": n_reviews,
            }
        )
    return render(request, "reviews/staff_events.html", {"events": events})


def staff_dashboard(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce

    backup_if_stale("auto")
    rows = roster_rows()
    summary = roster_summary(rows)
    pdf_status = submission_status_by_team()
    for row in rows:
        row["has_pdf"] = pdf_status.get(row["team_id"], False)
    last = latest_backup()
    return render(
        request,
        "reviews/staff_dashboard.html",
        {
            "rows": rows,
            "summary": summary,
            "import_form": RosterImportForm(),
            "add_form": AddStudentForm(),
            "group_names": existing_group_names(),
            "current_event": get_or_create_proposal_event(),
            "n_pdfs": sum(1 for ok in pdf_status.values() if ok),
            "n_groups_pdf": len(pdf_status),
            "last_backup": last.name if last else "",
            "focus_id": request.session.pop("roster_focus_id", None),
            "focus_note": request.session.pop("roster_focus_note", None),
            "focus_level": request.session.pop("roster_focus_level", "success"),
        },
    )


def _finish_roster_import(result):
    return (
        f"Imported {result['n']} students "
        f"({result['created']} new, {result['updated']} updated, "
        f"{result.get('skipped', 0)} skipped). "
        f"Issued {result['issued_ids']} Reviewer IDs and "
        f"created {result['assigned_tasks']} review assignments."
    )


@require_POST
def staff_import(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    form = RosterImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose a CSV or Excel file to import.")
        return redirect("staff_dashboard")
    try:
        records = parse_roster_file(form.cleaned_data["roster"])
        preview = preview_roster_import(records)
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    except Exception as exc:
        messages.error(request, f"Could not read that file: {exc}")
        return redirect("staff_dashboard")

    replace = bool(form.cleaned_data["replace"])
    needs_confirm = preview["n_conflicts"] or (replace and Student.objects.exists())
    if needs_confirm:
        request.session["pending_roster"] = {
            "records": records,
            "replace": replace,
        }
        return render(
            request,
            "reviews/staff_import_confirm.html",
            {
                "preview": preview,
                "replace": replace,
            },
        )
    lock = _acquire_import_lock()
    if lock is None:
        messages.error(request, "An import is already running. Wait until this page finishes loading, then refresh.")
        return redirect("staff_dashboard")
    try:
        create_backup("roster-import")
        result = import_roster(records, replace=False, on_conflict="update")
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    finally:
        _release_import_lock(lock)
    messages.success(request, _finish_roster_import(result))
    return redirect("staff_dashboard")


@require_POST
def staff_import_confirm(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    pending = request.session.pop("pending_roster", None)
    if not pending:
        messages.error(request, "That import expired. Upload the file again.")
        return redirect("staff_dashboard")
    action = request.POST.get("action")
    if action == "cancel":
        messages.success(request, "Import cancelled. Nothing was changed.")
        return redirect("staff_dashboard")
    on_conflict = "skip" if action == "skip" else "update"
    if action == "replace":
        on_conflict = "update"
    lock = _acquire_import_lock()
    if lock is None:
        messages.error(request, "An import is already running. Wait until this page finishes loading, then refresh.")
        return redirect("staff_dashboard")
    try:
        create_backup("roster-import")
        result = import_roster(
            pending["records"],
            replace=bool(pending.get("replace") and action == "replace"),
            on_conflict=on_conflict,
        )
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    except Exception as exc:
        messages.error(request, f"Import failed: {exc}")
        return redirect("staff_dashboard")
    finally:
        _release_import_lock(lock)
    messages.success(request, _finish_roster_import(result))
    return redirect("staff_dashboard")


@require_POST
def staff_upload_pdfs(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    files = request.FILES.getlist("pdfs")
    if not files:
        messages.error(request, "Choose PDF files, or a zip of PDFs named by group id.")
        return redirect("staff_dashboard")
    try:
        uploads = collect_pdf_uploads(files)
        match = match_pdfs_to_roster(uploads)
        if not Team.objects.exists():
            raise RosterError("Import the student list first, then upload PDFs named by those group ids.")
        create_backup("pdf-upload")
        updated = apply_pdf_uploads(match)
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    except Exception as exc:
        messages.error(request, f"PDF upload failed: {exc}")
        return redirect("staff_dashboard")
    extras = ", ".join(item["filename"] for item in match["extras"])
    missing = ", ".join(match["missing"])
    note = f"Stored {updated} group PDF(s)."
    if extras:
        note += f" Not on the roster, so skipped: {extras}."
    if missing:
        note += f" Roster groups still missing a PDF: {missing}."
    if extras or missing:
        messages.error(request, note)
    else:
        messages.success(request, note)
    return redirect("staff_dashboard")


@require_POST
def staff_backup_now(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    dest = create_backup("manual")
    messages.success(request, f"Backup saved as {dest.name}.")
    return redirect("staff_dashboard")


@require_POST
def staff_set_event_lock(request, event_id):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    event = get_object_or_404(ReviewEvent, pk=event_id)
    action = request.POST.get("action")
    if action == "lock":
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            messages.error(request, "Write a reason before locking. Students will see that sentence.")
            return redirect("staff_dashboard")
        event.is_open = False
        event.lock_reason = reason
        event.save(update_fields=["is_open", "lock_reason"])
        messages.success(
            request,
            f"{event.title} is locked. Students cannot submit or edit reviews.",
        )
    elif action == "reopen":
        event.is_open = True
        event.lock_reason = ""
        event.save(update_fields=["is_open", "lock_reason"])
        messages.success(request, f"{event.title} is open again. Students can submit and edit.")
    else:
        messages.error(request, "Unknown lock action.")
    return redirect("staff_dashboard")


@require_POST
def staff_add_student(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    form = AddStudentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Name, UID, email, and group are required to add a student.")
        return redirect("staff_dashboard")
    try:
        result = add_student(
            name=form.cleaned_data["name"],
            uid=form.cleaned_data["uid"],
            email=form.cleaned_data["email"],
            group=form.cleaned_data["group"],
            password=form.cleaned_data["password"],
            reviewer_id=form.cleaned_data["reviewer_id"],
        )
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    student = result["student"]
    return _redirect_roster(
        request,
        student=student,
        note=(
            f"Added {student.name} ({student.student_id}) in {student.team.name}. "
            f"Reviewer ID {result['reviewer_id']}. Issued password {result['password']}."
        ),
    )


@require_POST
def staff_delete_student(request, pk):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    student = get_object_or_404(Student, pk=pk)
    try:
        create_backup("delete-student")
        info = delete_student(student)
    except Exception as exc:
        messages.error(request, f"Could not delete that student: {exc}")
        return redirect("staff_dashboard")
    messages.success(request, f"Deleted {info['name']} ({info['student_id']}). A backup was saved first.")
    return redirect("staff_dashboard")


@require_POST
def staff_change_group(request, pk):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    student = get_object_or_404(Student, pk=pk)
    form = ChangeGroupForm(request.POST)
    if not form.is_valid():
        return _redirect_roster(request, student=student, note="A group is required.", level="error")
    try:
        result = change_student_group(student, form.cleaned_data["group"])
    except RosterError as exc:
        return _redirect_roster(request, student=student, note=str(exc), level="error")
    student.refresh_from_db()
    if not result["changed"]:
        return _redirect_roster(
            request,
            student=student,
            note=f"{student.name} is already in {result['new_group']}.",
        )
    extra = ""
    if result["removed_own_reviews"]:
        extra = " Removed review task(s) for their new group."
    return _redirect_roster(
        request,
        student=student,
        note=f"Moved {student.name} from {result['old_group']} to {result['new_group']}.{extra}",
    )


@require_POST
def staff_change_password(request, pk):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    student = get_object_or_404(Student, pk=pk)
    form = ChangePasswordForm(request.POST)
    if not form.is_valid():
        return _redirect_roster(
            request, student=student, note="Could not update that password.", level="error"
        )
    create_backup("password-change")
    raw = reset_student_password(student, form.cleaned_data["password"])
    return _redirect_roster(
        request,
        student=student,
        note=f"Password changed for {student.name} ({student.student_id}). New password: {raw}",
    )


@require_POST
def staff_issue_ids(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    created = issue_missing_ids()
    if created:
        messages.success(request, f"Issued {created} Reviewer ID(s). Students log in with the issued password.")
    else:
        messages.success(request, "Every student already has a Reviewer ID.")
    return redirect("staff_dashboard")


def _per_student_from_request(request) -> int | None:
    raw = (request.POST.get("per_student") or "1").strip()
    try:
        count = int(raw)
    except ValueError:
        return None
    if count < 1 or count > 10:
        return None
    return count


@require_POST
def staff_assign_reviews(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    per_student = _per_student_from_request(request)
    if per_student is None:
        messages.error(request, "Enter a number from 1 to 10 for proposals each student reviews.")
        return redirect("staff_dashboard")
    preview = review_assignment_preview()
    if preview["n_existing_tasks"]:
        request.session["pending_assign_count"] = per_student
        return render(
            request,
            "reviews/staff_assign_confirm.html",
            {"preview": preview, "per_student": per_student},
        )
    try:
        result = assign_event_reviews(per_student, replace=False)
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    messages.success(
        request,
        f"Assigned {result['per_student']} proposal(s) each to {result['reviewers']} student(s).",
    )
    return redirect("staff_dashboard")


@require_POST
def staff_assign_reviews_confirm(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    per_student = request.session.pop("pending_assign_count", None)
    if not per_student:
        messages.error(request, "That assignment expired. Choose the number again.")
        return redirect("staff_dashboard")
    if request.POST.get("action") != "replace":
        messages.success(request, "Assignment cancelled. Existing tasks were kept.")
        return redirect("staff_dashboard")
    try:
        result = assign_event_reviews(int(per_student), replace=True)
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_dashboard")
    messages.success(
        request,
        (
            f"Replaced existing tasks. Each of {result['reviewers']} student(s) "
            f"now has {result['per_student']} proposal(s)."
        ),
    )
    return redirect("staff_dashboard")


def staff_roster_template(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    response = HttpResponse(template_csv_bytes(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="roster_template.csv"'
    return response


def staff_sample_roster(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    path = settings.BASE_DIR / "fixtures" / "students_test.csv"
    return FileResponse(path.open("rb"), as_attachment=True, filename="students_test.csv")


def staff_credentials(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    response = HttpResponse(credentials_csv_bytes(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="student_credentials.csv"'
    return response


def staff_export(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce

    reviews = Review.objects.select_related(
        "assignment__event",
        "assignment__reviewer",
        "assignment__proposal",
        "assignment__proposal__team",
    ).order_by(
        "assignment__event__slug",
        "assignment__proposal__team__name",
        "assignment__reviewer__code",
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="anonymous_reviews.csv"'
    writer = csv.writer(response)
    header = (
        ["event", "team", "submission_title", "reviewer_id"]
        + [name for name, _label, _maximum, _part in CRITERIA]
        + ["content_total", "delivery_total", "total", "counted", "suggestions", "submitted_at"]
    )
    writer.writerow(header)
    for review in reviews:
        writer.writerow(
            [
                review.assignment.event.slug,
                review.assignment.proposal.team.name,
                review.assignment.proposal.title,
                review.assignment.reviewer.code,
                *[getattr(review, name) for name, _label, _maximum, _part in CRITERIA],
                review.content_total,
                review.delivery_total,
                review.total,
                "yes" if review.counted else "no",
                review.suggestions,
                review.submitted_at.isoformat(timespec="seconds"),
            ]
        )
    return response


def staff_stats(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce

    proposals = Proposal.objects.select_related("team", "event").order_by(
        "event__pk", "team__name"
    )
    rows = []
    for proposal in proposals:
        reviews = list(
            Review.objects.filter(assignment__proposal=proposal).select_related(
                "assignment__reviewer"
            )
        )
        stats = proposal_review_stats(reviews)
        rows.append(
            {
                "event": proposal.event.title,
                "team": proposal.team.name,
                "team_id": proposal.team_id,
                "title": proposal.title,
                "has_pdf": bool(proposal.file),
                **stats,
            }
        )
    return render(request, "reviews/staff_stats.html", {"rows": rows})


def staff_pdf_library(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    rows = pdf_library_rows()
    return render(
        request,
        "reviews/staff_pdf_library.html",
        {
            "rows": rows,
            "n_ready": sum(1 for row in rows if row["has_pdf"]),
        },
    )


@require_POST
def staff_replace_group_pdf(request, team_id):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    team = get_object_or_404(Team, pk=team_id)
    uploaded = request.FILES.get("pdf")
    if uploaded is None:
        messages.error(request, "Choose a PDF to replace this group's file.")
        return redirect("staff_team_stats", team_id=team.pk)
    try:
        create_backup("replace-pdf")
        proposal = replace_group_pdf(team, uploaded)
    except RosterError as exc:
        messages.error(request, str(exc))
        return redirect("staff_team_stats", team_id=team.pk)
    except Exception as exc:
        messages.error(request, f"Could not replace that PDF: {exc}")
        return redirect("staff_team_stats", team_id=team.pk)
    messages.success(
        request,
        f"Replaced the PDF for {team.name}. Students download it as {proposal.download_name}.",
    )
    return redirect("staff_team_stats", team_id=team.pk)


def staff_proposal_pdf(request, team_id):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    team = get_object_or_404(Team, pk=team_id)
    event = get_or_create_proposal_event()
    proposal = get_object_or_404(Proposal, team=team, event=event)
    if not proposal.file:
        raise Http404
    response = FileResponse(proposal.file.open("rb"), content_type="application/pdf")
    safe_name = team.name.replace(" ", "-")
    response["Content-Disposition"] = f'inline; filename="{safe_name}.pdf"'
    return response


def staff_team_stats(request, team_id):
    bounce = _require_staff(request)
    if bounce:
        return bounce

    team = get_object_or_404(Team, pk=team_id)
    event = get_or_create_proposal_event()
    proposal = get_object_or_404(Proposal, team=team, event=event)
    reviews = list(
        Review.objects.filter(assignment__proposal=proposal)
        .select_related("assignment__reviewer")
        .order_by("assignment__reviewer__code")
    )
    stats = proposal_review_stats(reviews)
    rows = [
        {
            "review": review,
            "flagged": stats["flagged"].get(review.pk, False),
        }
        for review in reviews
    ]
    members = list(team.members.select_related("identity").order_by("student_id"))
    incoming_assignments = list(
        ReviewAssignment.objects.filter(proposal=proposal)
        .select_related("reviewer__student")
        .order_by("reviewer__code")
    )
    pending = [
        assignment
        for assignment in incoming_assignments
        if not Review.objects.filter(assignment=assignment).exists()
    ]
    return render(
        request,
        "reviews/staff_team_stats.html",
        {
            "team": team,
            "proposal": proposal,
            "rows": rows,
            "stats": stats,
            "members": members,
            "has_pdf": bool(proposal.file),
            "n_assigned": len(incoming_assignments),
            "pending": pending,
        },
    )


def staff_student_detail(request, pk):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    student = get_object_or_404(Student.objects.select_related("team", "identity"), pk=pk)
    identity = getattr(student, "identity", None)
    tasks = []
    if identity:
        for assignment in (
            ReviewAssignment.objects.filter(reviewer=identity)
            .select_related("event", "proposal__team")
            .order_by("event__pk", "proposal__team__name")
        ):
            review = _review_of(assignment)
            tasks.append(
                {
                    "assignment": assignment,
                    "review": review,
                    "done": review is not None,
                }
            )
    return render(
        request,
        "reviews/staff_student.html",
        {
            "student": student,
            "identity": identity,
            "tasks": tasks,
            "n_assigned": len(tasks),
            "n_submitted": sum(1 for task in tasks if task["done"]),
        },
    )


def staff_stats_export(request):
    bounce = _require_staff(request)
    if bounce:
        return bounce
    proposals = Proposal.objects.select_related("team", "event").order_by(
        "event__pk", "team__name"
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="review_statistics.csv"'
    writer = csv.writer(response)
    header = [
        "event",
        "team",
        "title",
        "has_pdf",
        "received",
        "counted",
        "flagged",
        "excluded",
        "total_mean",
        "total_median",
        "total_min",
        "total_max",
        "content_mean",
        "content_median",
        "content_min",
        "content_max",
        "delivery_mean",
        "delivery_median",
        "delivery_min",
        "delivery_max",
    ]
    for name, _label, _maximum, _part in CRITERIA:
        header.extend(
            [
                f"{name}_mean",
                f"{name}_median",
                f"{name}_min",
                f"{name}_max",
            ]
        )
    writer.writerow(header)

    def _cells(summary):
        return [
            summary["mean"] if summary["mean"] is not None else "",
            summary["median"] if summary["median"] is not None else "",
            summary["min"] if summary["min"] is not None else "",
            summary["max"] if summary["max"] is not None else "",
        ]

    for proposal in proposals:
        reviews = list(Review.objects.filter(assignment__proposal=proposal))
        stats = proposal_review_stats(reviews)
        row = [
            proposal.event.title,
            proposal.team.name,
            proposal.title,
            "yes" if proposal.file else "no",
            stats["n"],
            stats["n_counted"],
            stats["n_flagged"],
            stats["n_excluded"],
            *_cells(stats),
            *_cells(stats["content"]),
            *_cells(stats["delivery"]),
        ]
        for name, _label, _maximum, _part in CRITERIA:
            row.extend(_cells(stats["parts"][name]))
        writer.writerow(row)
    return response


@require_POST
def staff_toggle_review(request, team_id, review_id):
    bounce = _require_staff(request)
    if bounce:
        return bounce

    review = get_object_or_404(
        Review,
        pk=review_id,
        assignment__proposal__team_id=team_id,
    )
    review.counted = not review.counted
    review.save(update_fields=["counted"])
    return redirect("staff_team_stats", team_id=team_id)
