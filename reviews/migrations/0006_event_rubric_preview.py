import secrets

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion

from reviews.models import submission_upload_to


def backfill_events(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    Review.objects.all().delete()
    ReviewEvent = apps.get_model("reviews", "ReviewEvent")
    event = ReviewEvent.objects.create(
        slug="w5-proposal",
        title="W5 Proposal review",
        kind="proposal",
        description="Anonymous review of another group's project proposal.",
        is_open=True,
    )
    Proposal = apps.get_model("reviews", "Proposal")
    for proposal in Proposal.objects.all():
        proposal.event_id = event.pk
        proposal.file_token = secrets.token_hex(8)
        proposal.save()
    ReviewAssignment = apps.get_model("reviews", "ReviewAssignment")
    for assignment in ReviewAssignment.objects.all():
        assignment.event_id = event.pk
        assignment.save()


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0005_student_password"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("title", models.CharField(max_length=128)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("proposal", "Proposal"),
                            ("final_report", "Final report"),
                            ("other", "Other"),
                        ],
                        default="proposal",
                        max_length=32,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("is_open", models.BooleanField(default=True)),
            ],
            options={"ordering": ["pk"]},
        ),
        migrations.AddField(
            model_name="proposal",
            name="event",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="submissions",
                to="reviews.reviewevent",
            ),
        ),
        migrations.AddField(
            model_name="proposal",
            name="file_token",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="team",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="submissions",
                to="reviews.team",
            ),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="file",
            field=models.FileField(upload_to=submission_upload_to),
        ),
        migrations.AddField(
            model_name="reviewassignment",
            name="event",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assignments",
                to="reviews.reviewevent",
            ),
        ),
        migrations.RunPython(backfill_events, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="proposal",
            name="file_token",
            field=models.CharField(blank=True, max_length=32, unique=True),
        ),
        migrations.AlterField(
            model_name="proposal",
            name="event",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="submissions",
                to="reviews.reviewevent",
            ),
        ),
        migrations.AlterField(
            model_name="reviewassignment",
            name="event",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assignments",
                to="reviews.reviewevent",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="proposal",
            unique_together={("event", "team")},
        ),
        migrations.AlterUniqueTogether(
            name="reviewassignment",
            unique_together={("event", "reviewer", "proposal")},
        ),
        migrations.RemoveField(model_name="review", name="problem_user"),
        migrations.RemoveField(model_name="review", name="data_permission"),
        migrations.RemoveField(model_name="review", name="method"),
        migrations.RemoveField(model_name="review", name="scope"),
        migrations.RemoveField(model_name="review", name="feasibility"),
        migrations.RemoveField(model_name="review", name="expression"),
        migrations.RemoveField(model_name="review", name="action_line"),
        migrations.AddField(
            model_name="review",
            name="background",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="review",
            name="pipeline",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(12),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="review",
            name="evaluation",
            field=models.PositiveSmallIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(8),
                ]
            ),
        ),
        migrations.AddField(
            model_name="review",
            name="distribution",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="review",
            name="ethics",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="review",
            name="checkpoints",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="review",
            name="argumentation",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="review",
            name="presentation",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(model_name="review", name="background_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="pipeline_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="evaluation_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="distribution_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="ethics_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="checkpoints_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="argumentation_note", field=models.CharField(blank=True, max_length=240)),
        migrations.AddField(model_name="review", name="presentation_note", field=models.CharField(blank=True, max_length=240)),
    ]
