from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reviews.models import (
    CourseStaff,
    Proposal,
    Review,
    ReviewAssignment,
    ReviewEvent,
    ReviewerIdentity,
    Student,
    Team,
)
from reviews.pdf import make_chart_figure, make_pipeline_figure, write_illustrated_pdf
from reviews.proposal_content import PROPOSALS
from reviews.services import assign_reviews, generate_reviewer_code, get_or_create_proposal_event

STUDENTS = [
    ("A001", "Alex Chen", "Team A"),
    ("A002", "Blair Ng", "Team A"),
    ("A003", "Casey Wu", "Team A"),
    ("9000000001", "Demo Reviewer", "Team A"),
    ("B001", "Drew Patel", "Team B"),
    ("B002", "Eden Li", "Team B"),
    ("B003", "Fran Ho", "Team B"),
    ("C001", "Gray Kim", "Team C"),
    ("C002", "Harper Xu", "Team C"),
    ("C003", "Ivan Zhou", "Team C"),
    ("D001", "Jules Tan", "Team D"),
    ("D002", "Kai Morse", "Team D"),
    ("D003", "Lane Yip", "Team D"),
]

UNCLAIMED_TEAMS = {"Team D"}

SAMPLE_REVIEW = {
    "background": 4,
    "pipeline": 9,
    "evaluation": 6,
    "distribution": 4,
    "ethics": 4,
    "checkpoints": 3,
    "argumentation": 4,
    "presentation": 4,
    "evaluation_note": "Name the frozen snapshot date in the method section.",
    "suggestions": "Name the frozen snapshot date and add two refusal examples to the evaluation set.",
}

LOW_REVIEW = {
    "background": 1,
    "pipeline": 2,
    "evaluation": 1,
    "distribution": 1,
    "ethics": 1,
    "checkpoints": 1,
    "argumentation": 1,
    "presentation": 1,
    "pipeline_note": "The pipeline is too vague to mark.",
    "suggestions": "Rewrite the user, data, and evaluation sections before this can be marked fairly.",
}


def email_for(name: str) -> str:
    parts = name.lower().split()
    return f"{parts[0]}.{parts[-1]}@hku.hk"


class Command(BaseCommand):
    help = "Reset demo roster, richer fake proposals, some claimed IDs, sample reviews."

    def handle(self, *args, **options):
        with transaction.atomic():
            Review.objects.all().delete()
            ReviewAssignment.objects.all().delete()
            Proposal.objects.all().delete()
            ReviewerIdentity.objects.all().delete()
            CourseStaff.objects.all().delete()
            Student.objects.all().delete()
            Team.objects.all().delete()
            ReviewEvent.objects.all().delete()

            event = get_or_create_proposal_event()
            teams = {}
            for team_name, payload in PROPOSALS.items():
                teams[team_name] = Team.objects.create(name=team_name)
                self._attach_proposal(event, teams[team_name], payload)

            for student_id, full_name, team_name in STUDENTS:
                if student_id == "9000000001":
                    email = "demo.reviewer@fixture.hku.hk"
                else:
                    email = email_for(full_name)
                student = Student.objects.create(
                    student_id=student_id,
                    name=full_name,
                    email=email,
                    team=teams[team_name],
                )
                student.set_login_password("ailt9019")

            CourseStaff.objects.create(
                uid="9000000003",
                name="Demo Reviewer",
                email="demo.reviewer@fixture.hku.hk",
                registered=True,
            )

            to_claim = list(
                Student.objects.select_related("team")
                .exclude(team__name__in=UNCLAIMED_TEAMS)
                .order_by("pk")
            )
            existing: set[str] = set()
            reviewers = []
            for student in to_claim:
                code = generate_reviewer_code(existing)
                existing.add(code)
                reviewers.append(
                    ReviewerIdentity.objects.create(
                        student=student,
                        code=code,
                        activated_at=timezone.now(),
                    )
                )

            proposals = list(Proposal.objects.select_related("team", "event"))
            pairs = assign_reviews(reviewers, proposals, per_student=2)
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
            self._seed_sample_reviews()

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("Student login: http://127.0.0.1:8000/login  (UID or Reviewer ID + password ailt9019)")
        self.stdout.write("Teacher login:  http://127.0.0.1:8000/admin/login  (configure LEGACY_STAFF_PASSWORD before startup)")
        self.stdout.write("Your student UID 9000000001 / demo.reviewer@fixture.hku.hk is already issued.")
        self.stdout.write("")
        self.stdout.write("Issued student accounts (password for all: ailt9019):")
        for identity in ReviewerIdentity.objects.select_related("student").order_by("student__student_id"):
            self.stdout.write(
                f"  {identity.student.student_id}  {identity.student.email}  {identity.code}"
            )
        self.stdout.write("")
        self.stdout.write("Team D has passwords but no Reviewer IDs yet — use staff Issue IDs to test that path:")
        for student in Student.objects.filter(team__name__in=UNCLAIMED_TEAMS).order_by("student_id"):
            self.stdout.write(f"  {student.student_id}  {student.email}")

    def _attach_proposal(self, event: ReviewEvent, team: Team, payload: dict) -> None:
        fig_dir = Path(settings.MEDIA_ROOT) / "tmp_pdf"
        pipeline = make_pipeline_figure(
            fig_dir / f"{team.pk}-pipe.jpg",
            "Project pipeline",
            ["Ask", "Retrieve", "Cite", "Refuse"],
        )
        chart = make_chart_figure(
            fig_dir / f"{team.pk}-eval.jpg",
            "Planned evaluation",
            [("Correct", 8), ("Cited", 7), ("Refuse", 3)],
        )
        pdf_path = fig_dir / f"{team.pk}-submission.pdf"
        write_illustrated_pdf(
            pdf_path,
            payload["title"],
            [payload["abstract"]] + payload["pdf_lines"],
            [pipeline, chart],
        )
        proposal = Proposal(
            event=event,
            team=team,
            title=payload["title"],
            keywords=payload["keywords"],
            abstract=payload["abstract"],
            body=payload["body"],
        )
        proposal.save()
        with pdf_path.open("rb") as handle:
            proposal.file.save(proposal.download_name, File(handle), save=True)

    def _seed_sample_reviews(self) -> None:
        team_a = Proposal.objects.get(team__name="Team A")
        incoming = list(
            ReviewAssignment.objects.filter(proposal=team_a).select_related("reviewer")[:4]
        )
        payloads = [
            SAMPLE_REVIEW,
            SAMPLE_REVIEW,
            {**SAMPLE_REVIEW, "presentation": 3},
            LOW_REVIEW,
        ]
        for assignment, scores in zip(incoming, payloads):
            Review.objects.create(assignment=assignment, **scores)

        alex = ReviewerIdentity.objects.filter(student__student_id="A001").first()
        if alex is None:
            return
        outgoing = (
            ReviewAssignment.objects.filter(reviewer=alex, review__isnull=True).first()
        )
        if outgoing:
            Review.objects.create(assignment=outgoing, **SAMPLE_REVIEW)
