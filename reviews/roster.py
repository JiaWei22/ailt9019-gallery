import csv
import io
import re

from django.db import transaction

from .models import Proposal, Review, ReviewAssignment, ReviewEvent, ReviewerIdentity, Student, Team
from .services import (
    assign_reviews,
    generate_login_password,
    generate_reviewer_code,
    get_or_create_proposal_event,
)

COLUMN_ALIASES = {
    "name": {"name", "student name", "full name", "student"},
    "uid": {
        "uid",
        "student_id",
        "student id",
        "student_number",
        "student number",
        "hku uid",
        "university id",
    },
    "email": {"email", "hku email", "mail", "e-mail"},
    "group": {
        "group",
        "team",
        "group_number",
        "group number",
        "group_name",
        "group name",
        "group_id",
        "group id",
    },
    "reviewer_id": {"reviewer_id", "reviewer id", "review id", "reviewer"},
    "review_groups": {
        "review_groups",
        "groups to review",
        "review groups",
        "assigned groups",
        "review_group",
    },
    "password": {"password", "initial password", "login password", "pass"},
}

ROSTER_TEMPLATE_HEADERS = [
    "name",
    "uid",
    "email",
    "group",
    "reviewer_id",
    "review_groups",
    "password",
]


class RosterError(ValueError):
    pass


def normalize_group_name(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise RosterError("A group is required.")
    text = re.sub(r"^(team|group)\s+", "", text, flags=re.IGNORECASE)
    if re.fullmatch(r"[A-Za-z]", text):
        return f"Group {text.upper()}"
    if re.fullmatch(r"\d+", text):
        return f"Group {int(text)}"
    return f"Group {text}"


def group_sort_key(name: str):
    text = (name or "").strip()
    number = re.search(r"(\d+)$", text)
    if number:
        return (0, int(number.group(1)), text.lower())
    letter = re.search(r"\b([A-Za-z])$", text)
    if letter:
        return (1, ord(letter.group(1).upper()), text.lower())
    return (2, 0, text.lower())


def normalize_reviewer_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        return ""
    if not code.startswith("R-"):
        code = f"R-{code.lstrip('-')}"
    return code


def split_review_groups(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[;,|]", value)
    return [normalize_group_name(part) for part in parts if part.strip()]


def _header_map(headers: list[str]) -> dict[str, int]:
    found = {}
    for index, raw in enumerate(headers):
        key = (raw or "").strip().lower()
        for field, aliases in COLUMN_ALIASES.items():
            if key in aliases:
                found[field] = index
    missing = [
        name
        for name in ("name", "uid", "email", "group", "reviewer_id", "password")
        if name not in found
    ]
    if missing:
        raise RosterError(
            "The upload file needs columns: name, uid, email, group, reviewer_id, password. "
            "Optional: review_groups. Missing: "
            + ", ".join(missing)
        )
    return found


def _cell(row: list, index: int | None) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def parse_roster_file(uploaded) -> list[dict]:
    name = (getattr(uploaded, "name", "") or "").lower()
    data = uploaded.read()
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    if name.endswith(".xlsx"):
        rows = _parse_xlsx(data)
    else:
        text = data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RosterError("The file is empty.")
    mapping = _header_map(rows[0])
    records = []
    seen_uid = set()
    seen_email = set()
    seen_code = set()
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(_cell(row, i) for i in range(len(row))):
            continue
        record = {
            "name": _cell(row, mapping["name"]),
            "uid": _cell(row, mapping["uid"]),
            "email": _cell(row, mapping["email"]).lower(),
            "group": normalize_group_name(_cell(row, mapping["group"])),
            "reviewer_id": normalize_reviewer_code(
                _cell(row, mapping.get("reviewer_id"))
            ),
            "review_groups": split_review_groups(
                _cell(row, mapping.get("review_groups"))
            ),
            "password": _cell(row, mapping.get("password")),
        }
        if not record["name"] or not record["uid"] or not record["email"]:
            raise RosterError(f"Row {line_no} is missing name, UID, or email.")
        if not record["reviewer_id"] or not record["password"]:
            raise RosterError(
                f"Row {line_no} is missing reviewer_id or password. "
                "Issue them locally first with scripts/issue_credentials.py."
            )
        if record["uid"] in seen_uid:
            raise RosterError(f"UID {record['uid']} is repeated in the file.")
        if record["email"] in seen_email:
            raise RosterError(f"Email {record['email']} is repeated in the file.")
        if record["reviewer_id"] and record["reviewer_id"] in seen_code:
            raise RosterError(f"Reviewer ID {record['reviewer_id']} is repeated.")
        seen_uid.add(record["uid"])
        seen_email.add(record["email"])
        if record["reviewer_id"]:
            seen_code.add(record["reviewer_id"])
        records.append(record)
    if not records:
        raise RosterError("The file has a header but no students.")
    return records


def _parse_xlsx(data: bytes) -> list[list[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RosterError("Excel import needs openpyxl. Use CSV, or pip install openpyxl.") from exc
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook.active
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if cell is None else str(cell) for cell in row])
    return rows


def ensure_proposal(team: Team, event: ReviewEvent | None = None) -> Proposal:
    """Create the submission row only. Staff upload the real PDF afterwards.

    Generating a placeholder file here holds the database lock for every new
    group and makes a 300-student import exceed typical proxy timeouts.
    """
    event = event or get_or_create_proposal_event()
    existing = Proposal.objects.filter(event=event, team=team).first()
    if existing:
        return existing
    return Proposal.objects.create(
        event=event,
        team=team,
        title=f"{team.name} proposal",
    )


def secrets_token() -> str:
    import secrets

    return secrets.token_hex(8)


def clear_roster() -> None:
    Review.objects.all().delete()
    ReviewAssignment.objects.all().delete()
    ReviewerIdentity.objects.all().delete()
    Proposal.objects.all().delete()
    Student.objects.all().delete()
    Team.objects.all().delete()
    get_or_create_proposal_event()


def preview_roster_import(records: list[dict]) -> dict:
    existing = {
        student.student_id: student
        for student in Student.objects.select_related("team", "identity")
    }
    new_rows = []
    conflicts = []
    for record in records:
        student = existing.get(record["uid"])
        if student is None:
            new_rows.append(record)
            continue
        identity = getattr(student, "identity", None)
        conflicts.append(
            {
                **record,
                "current_name": student.name,
                "current_group": student.team.name,
                "current_reviewer_id": identity.code if identity else "",
                "current_password": student.issued_password,
            }
        )
    return {
        "records": records,
        "new": new_rows,
        "conflicts": conflicts,
        "n_new": len(new_rows),
        "n_conflicts": len(conflicts),
    }


@transaction.atomic
def import_roster(
    records: list[dict],
    *,
    replace: bool = False,
    on_conflict: str = "update",
) -> dict:
    if on_conflict not in {"update", "skip"}:
        raise RosterError("Choose whether to update or skip existing UIDs.")
    if replace:
        clear_roster()

    event = get_or_create_proposal_event()
    teams = {team.name: team for team in Team.objects.all()}
    created_students = 0
    updated_students = 0
    skipped_students = 0
    issued_ids = 0
    assigned_tasks = 0

    for record in records:
        team = teams.get(record["group"])
        if team is None:
            team = Team.objects.create(name=record["group"])
            teams[team.name] = team
            ensure_proposal(team, event)

        student = Student.objects.filter(student_id=record["uid"]).first()
        if student is None:
            student = Student.objects.create(
                student_id=record["uid"],
                name=record["name"],
                email=record["email"] or None,
                team=team,
            )
            created_students += 1
        elif on_conflict == "skip":
            skipped_students += 1
            continue
        else:
            student.name = record["name"]
            student.email = record["email"] or None
            student.team = team
            student.save(update_fields=["name", "email", "team"])
            updated_students += 1

        student.set_login_password(record["password"])

        identity = ReviewerIdentity.objects.filter(student=student).first()
        clash = (
            ReviewerIdentity.objects.filter(code=record["reviewer_id"])
            .exclude(student=student)
            .first()
        )
        if clash:
            raise RosterError(
                f"Reviewer ID {record['reviewer_id']} is already used by another student."
            )
        if identity is None:
            identity = ReviewerIdentity.objects.create(
                student=student,
                code=record["reviewer_id"],
                activated_at=None,
            )
            issued_ids += 1
        elif identity.code != record["reviewer_id"]:
            if identity.is_activated:
                raise RosterError(
                    f"UID {record['uid']} already logged in as {identity.code}. "
                    f"The file wants {record['reviewer_id']}. Change that row, or skip this UID."
                )
            identity.code = record["reviewer_id"]
            identity.save(update_fields=["code"])

        if identity and record["review_groups"]:
            assigned_tasks += _assign_named_groups(
                identity, record["review_groups"], teams, event
            )

    return {
        "created": created_students,
        "updated": updated_students,
        "skipped": skipped_students,
        "issued_ids": issued_ids,
        "assigned_tasks": assigned_tasks,
        "n": len(records),
    }


def _assign_named_groups(identity, group_names, teams, event: ReviewEvent) -> int:
    created = 0
    own = identity.student.team.name
    for group_name in group_names:
        if group_name == own:
            continue
        team = teams.get(group_name)
        if team is None:
            team = Team.objects.create(name=group_name)
            teams[group_name] = team
        proposal = ensure_proposal(team, event)
        _, was_created = ReviewAssignment.objects.get_or_create(
            event=event,
            reviewer=identity,
            proposal=proposal,
        )
        if was_created:
            created += 1
    return created


def resolve_group_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise RosterError("A group is required.")
    existing = {
        name.lower(): name for name in Team.objects.values_list("name", flat=True)
    }
    if raw.lower() in existing:
        return existing[raw.lower()]
    return normalize_group_name(raw)


def get_or_create_named_team(group: str) -> Team:
    team, _created = Team.objects.get_or_create(name=resolve_group_name(group))
    ensure_proposal(team)
    return team


def existing_group_names() -> list[str]:
    names = list(Team.objects.values_list("name", flat=True))
    names.sort(key=group_sort_key)
    return names


@transaction.atomic
def add_student(
    *,
    name: str,
    uid: str,
    email: str,
    group: str,
    password: str = "",
    reviewer_id: str = "",
) -> dict:
    name = (name or "").strip()
    uid = (uid or "").strip()
    email = (email or "").strip().lower()
    if not name or not uid or not email:
        raise RosterError("Name, UID, and email are required.")
    if Student.objects.filter(student_id=uid).exists():
        raise RosterError(f"UID {uid} is already on the roster.")
    if Student.objects.filter(email=email).exists():
        raise RosterError(f"Email {email} is already on the roster.")

    team = get_or_create_named_team(group)
    student = Student.objects.create(
        student_id=uid,
        name=name,
        email=email or None,
        team=team,
    )
    raw_password = (password or "").strip() or generate_login_password()
    student.set_login_password(raw_password)

    code = normalize_reviewer_code(reviewer_id)
    if code:
        if ReviewerIdentity.objects.filter(code=code).exists():
            raise RosterError(f"Reviewer ID {code} is already used.")
    else:
        codes = set(ReviewerIdentity.objects.values_list("code", flat=True))
        code = generate_reviewer_code(codes)
    ReviewerIdentity.objects.create(student=student, code=code, activated_at=None)
    return {
        "student": student,
        "password": raw_password,
        "reviewer_id": code,
    }


@transaction.atomic
def delete_student(student: Student) -> dict:
    snapshot = {
        "name": student.name,
        "student_id": student.student_id,
        "team": student.team.name,
    }
    student.delete()
    return snapshot


@transaction.atomic
def change_student_group(student: Student, group: str) -> dict:
    old_name = student.team.name
    team = get_or_create_named_team(group)
    if team.pk == student.team_id:
        return {
            "student": student,
            "changed": False,
            "old_group": old_name,
            "new_group": old_name,
            "removed_own_reviews": 0,
        }

    student.team = team
    student.save(update_fields=["team"])
    removed = 0
    identity = ReviewerIdentity.objects.filter(student=student).first()
    if identity:
        own_assignments = ReviewAssignment.objects.filter(
            reviewer=identity, proposal__team=team
        )
        removed = own_assignments.count()
        own_assignments.delete()
    return {
        "student": student,
        "changed": True,
        "old_group": old_name,
        "new_group": team.name,
        "removed_own_reviews": removed,
    }


def reset_student_password(student: Student, password: str = "") -> str:
    raw = (password or "").strip() or generate_login_password()
    student.set_login_password(raw)
    return raw


def issue_missing_ids() -> int:
    codes = set(ReviewerIdentity.objects.values_list("code", flat=True))
    created = 0
    for student in Student.objects.filter(identity__isnull=True).order_by("student_id"):
        if not student.password:
            student.set_login_password(generate_login_password())
        code = generate_reviewer_code(codes)
        codes.add(code)
        ReviewerIdentity.objects.create(student=student, code=code, activated_at=None)
        created += 1
    return created


def review_assignment_preview() -> dict:
    event = get_or_create_proposal_event()
    existing = ReviewAssignment.objects.filter(event=event)
    return {
        "n_reviewers": ReviewerIdentity.objects.count(),
        "n_people_with_tasks": existing.values("reviewer_id").distinct().count(),
        "n_existing_tasks": existing.count(),
        "n_submitted_reviews": Review.objects.filter(assignment__event=event).count(),
    }


def assign_event_reviews(per_student: int, *, replace: bool = False) -> dict:
    if per_student < 1:
        raise RosterError("Each student must review at least 1 proposal.")
    event = get_or_create_proposal_event()
    proposals = list(Proposal.objects.filter(event=event).select_related("team"))
    if len({proposal.team_id for proposal in proposals}) < 2:
        raise RosterError("Need at least two groups before assigning reviews.")
    if replace:
        ReviewAssignment.objects.filter(event=event).delete()
    reviewers = [
        identity
        for identity in ReviewerIdentity.objects.select_related("student")
        if replace or not identity.assignments.filter(event=event).exists()
    ]
    pairs = assign_reviews(reviewers, proposals, per_student=per_student)
    ReviewAssignment.objects.bulk_create(
        [
            ReviewAssignment(event=event, reviewer=reviewer, proposal=proposal)
            for reviewer, proposal in pairs
        ]
    )
    return {
        "reviewers": len(reviewers),
        "tasks": len(pairs),
        "per_student": per_student,
    }


def assign_missing_reviews(per_student: int = 1) -> int:
    result = assign_event_reviews(per_student, replace=False)
    return result["reviewers"]


def roster_rows() -> list[dict]:
    students = list(Student.objects.select_related("team").all())
    students.sort(key=lambda s: (group_sort_key(s.team.name), s.student_id))
    identity_by_student = {
        identity.student_id: identity
        for identity in ReviewerIdentity.objects.select_related("student")
    }
    identities = list(identity_by_student.values())
    assignment_map: dict[int, list] = {identity.pk: [] for identity in identities}
    submitted_ids = set(
        Review.objects.filter(assignment__reviewer__in=identities).values_list(
            "assignment_id", flat=True
        )
    )
    for assignment in ReviewAssignment.objects.filter(
        reviewer__in=identities
    ).select_related("proposal__team"):
        assignment_map.setdefault(assignment.reviewer_id, []).append(assignment)

    rows = []
    for student in students:
        identity = identity_by_student.get(student.id)
        assignments = assignment_map.get(identity.pk, []) if identity else []
        tasks = []
        submitted = 0
        for assignment in assignments:
            done = assignment.pk in submitted_ids
            if done:
                submitted += 1
            tasks.append(
                {
                    "group": assignment.proposal.team.name,
                    "done": done,
                }
            )
        tasks.sort(key=lambda item: group_sort_key(item["group"]))
        activated = bool(identity and identity.is_activated)
        rows.append(
            {
                "student": student,
                "name": student.name,
                "student_id": student.student_id,
                "email": student.email or "",
                "team": student.team.name,
                "team_id": student.team_id,
                "reviewer_id": identity.code if identity else "",
                "activated": activated,
                "activated_at": identity.activated_at if identity else None,
                "last_login_at": identity.last_login_at if identity else None,
                "assigned": len(tasks),
                "submitted": submitted,
                "tasks": tasks,
                "status": _account_status(identity, activated),
                "has_password": bool(student.password),
                "issued_password": student.issued_password,
            }
        )
    return rows


def _account_status(identity, activated: bool) -> str:
    if identity is None:
        return "no_id"
    if not activated:
        return "issued"
    return "active"


def roster_summary(rows: list[dict]) -> dict:
    groups = {row["team"] for row in rows}
    return {
        "n_students": len(rows),
        "n_groups": len(groups),
        "n_active": sum(1 for row in rows if row["status"] == "active"),
        "n_issued": sum(1 for row in rows if row["status"] == "issued"),
        "n_no_id": sum(1 for row in rows if row["status"] == "no_id"),
        "n_assigned": sum(row["assigned"] for row in rows),
        "n_submitted": sum(row["submitted"] for row in rows),
        "n_incomplete": sum(
            1 for row in rows if row["assigned"] and row["submitted"] < row["assigned"]
        ),
    }


def credentials_rows() -> list[dict]:
    rows = []
    for row in roster_rows():
        rows.append(
            {
                "name": row["name"],
                "uid": row["student_id"],
                "email": row["email"],
                "group": row["team"],
                "reviewer_id": row["reviewer_id"],
                "password": row["issued_password"],
                "status": row["status"],
                "last_login_at": row["last_login_at"].isoformat(timespec="seconds")
                if row["last_login_at"]
                else "",
                "assigned": row["assigned"],
                "submitted": row["submitted"],
                "groups_to_review": "; ".join(task["group"] for task in row["tasks"]),
                "groups_submitted": "; ".join(
                    task["group"] for task in row["tasks"] if task["done"]
                ),
            }
        )
    return rows


def credentials_csv_bytes() -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "name",
            "uid",
            "email",
            "group",
            "reviewer_id",
            "password",
            "status",
            "last_login_at",
            "assigned",
            "submitted",
            "groups_to_review",
            "groups_submitted",
        ]
    )
    for row in credentials_rows():
        writer.writerow(
            [
                row["name"],
                row["uid"],
                row["email"],
                row["group"],
                row["reviewer_id"],
                row["password"],
                row["status"],
                row["last_login_at"],
                row["assigned"],
                row["submitted"],
                row["groups_to_review"],
                row["groups_submitted"],
            ]
        )
    return buffer.getvalue().encode("utf-8")


def template_csv_bytes() -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ROSTER_TEMPLATE_HEADERS)
    writer.writerow(
        [
            "Andy",
            "9000000002",
            "demo.reviewer@fixture.hku.hk",
            "A",
            "",
            "B;C",
            "AndyLab26",
        ]
    )
    return buffer.getvalue().encode("utf-8")
