import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# Course rubric: Content /40 + Delivery /10 = 50.
CRITERIA = (
    ("background", "Background", 5, "Content"),
    ("pipeline", "Project pipeline", 12, "Content"),
    ("evaluation", "Evaluation and test", 8, "Content"),
    ("distribution", "Distribution and accessibility", 5, "Content"),
    ("ethics", "Ethics and risks", 5, "Content"),
    ("checkpoints", "Checkpoints", 5, "Content"),
    ("argumentation", "Argumentation", 5, "Delivery"),
    ("presentation", "Presentation", 5, "Delivery"),
)
CONTENT_CRITERIA = tuple(row for row in CRITERIA if row[3] == "Content")
DELIVERY_CRITERIA = tuple(row for row in CRITERIA if row[3] == "Delivery")
DIMENSIONS = tuple((name, label, maximum) for name, label, maximum, _part in CRITERIA)


def submission_upload_to(instance, filename):
    token = instance.file_token or secrets.token_hex(8)
    slug = instance.event.slug if instance.event_id else "unassigned"
    return f"submissions/{slug}/{token}.pdf"


class Team(models.Model):
    name = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    student_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    email = models.EmailField(unique=True, null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    password = models.CharField(max_length=128, blank=True)
    issued_password = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f"{self.student_id} {self.name}"

    def set_login_password(self, raw: str, *, save: bool = True) -> None:
        self.password = make_password(raw)
        self.issued_password = raw
        if save:
            self.save(update_fields=["password", "issued_password"])

    def check_login_password(self, raw: str) -> bool:
        if not self.password or not raw:
            return False
        return check_password(raw, self.password)


class ReviewerIdentity(models.Model):
    """Semester-unique alias. Never expose student <-> code on student pages or exports."""

    code = models.CharField(max_length=16, unique=True)
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name="identity"
    )
    claimed_at = models.DateTimeField(default=timezone.now)
    activated_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code

    @property
    def is_activated(self) -> bool:
        return self.activated_at is not None


class ReviewEvent(models.Model):
    """A review campaign. W5 proposals now; later a final-report event can reuse assignments."""

    KIND_PROPOSAL = "proposal"
    KIND_REPORT = "final_report"
    KIND_OTHER = "other"
    KIND_CHOICES = (
        (KIND_PROPOSAL, "Proposal"),
        (KIND_REPORT, "Final report"),
        (KIND_OTHER, "Other"),
    )

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=128)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_PROPOSAL)
    description = models.TextField(blank=True)
    is_open = models.BooleanField(default=True)
    lock_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.title

    def lock_message(self) -> str:
        reason = (self.lock_reason or "").strip() or "the deadline has passed"
        return f"It's currently locked due to {reason}."


class CourseStaff(models.Model):
    """Teaching-staff list. Registration is not open to students."""

    uid = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    email = models.EmailField(null=True, blank=True)
    registered = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.uid} {self.name}"


class Proposal(models.Model):
    """One team's artifact inside a review event (proposal now, report later)."""

    event = models.ForeignKey(
        ReviewEvent, on_delete=models.CASCADE, related_name="submissions"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="submissions")
    title = models.CharField(max_length=200)
    keywords = models.CharField(max_length=200, blank=True)
    abstract = models.TextField(blank=True)
    body = models.TextField(blank=True)
    file = models.FileField(upload_to=submission_upload_to)
    file_token = models.CharField(max_length=32, unique=True, blank=True)

    class Meta:
        unique_together = [("event", "team")]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.file_token:
            self.file_token = secrets.token_hex(8)
        super().save(*args, **kwargs)

    @property
    def download_name(self) -> str:
        return f"submission-{self.file_token}.pdf"

    @property
    def anonymous_title(self) -> str:
        token = (self.file_token or "paper")[:8]
        return f"Submission {token}"


class ReviewAssignment(models.Model):
    event = models.ForeignKey(
        ReviewEvent, on_delete=models.CASCADE, related_name="assignments"
    )
    reviewer = models.ForeignKey(
        ReviewerIdentity, on_delete=models.CASCADE, related_name="assignments"
    )
    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="assignments"
    )

    class Meta:
        unique_together = [("event", "reviewer", "proposal")]

    def __str__(self):
        return f"{self.event.slug}: {self.reviewer.code} -> {self.proposal.title}"


class Review(models.Model):
    assignment = models.OneToOneField(
        ReviewAssignment, on_delete=models.CASCADE, related_name="review"
    )
    background = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    pipeline = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(12)]
    )
    evaluation = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(8)]
    )
    distribution = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    ethics = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    checkpoints = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    argumentation = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    presentation = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    background_note = models.CharField(max_length=240, blank=True)
    pipeline_note = models.CharField(max_length=240, blank=True)
    evaluation_note = models.CharField(max_length=240, blank=True)
    distribution_note = models.CharField(max_length=240, blank=True)
    ethics_note = models.CharField(max_length=240, blank=True)
    checkpoints_note = models.CharField(max_length=240, blank=True)
    argumentation_note = models.CharField(max_length=240, blank=True)
    presentation_note = models.CharField(max_length=240, blank=True)
    suggestions = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edit_allowed = models.BooleanField(default=False)
    edit_requested_at = models.DateTimeField(null=True, blank=True)
    counted = models.BooleanField(default=True)

    def score_rows(self):
        rows = []
        for name, label, maximum, part in CRITERIA:
            rows.append(
                {
                    "name": name,
                    "part": part,
                    "label": label,
                    "maximum": maximum,
                    "score": getattr(self, name),
                    "note": getattr(self, f"{name}_note"),
                }
            )
        return rows

    def content_pairs(self):
        return [(row["label"], row["score"]) for row in self.score_rows() if row["part"] == "Content"]

    @property
    def content_total(self):
        return sum(getattr(self, name) for name, _label, _maximum, part in CRITERIA if part == "Content")

    @property
    def delivery_total(self):
        return sum(getattr(self, name) for name, _label, _maximum, part in CRITERIA if part == "Delivery")

    @property
    def dimension_total(self):
        return self.content_total

    @property
    def total(self):
        return self.content_total + self.delivery_total
