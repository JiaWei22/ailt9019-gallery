from django.db import migrations, models
from django.utils import timezone


def mark_existing_identities_activated(apps, schema_editor):
    ReviewerIdentity = apps.get_model("reviews", "ReviewerIdentity")
    now = timezone.now()
    ReviewerIdentity.objects.filter(activated_at__isnull=True).update(activated_at=now)


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0003_review_counted"),
    ]

    operations = [
        migrations.AddField(
            model_name="revieweridentity",
            name="activated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revieweridentity",
            name="last_login_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_identities_activated, migrations.RunPython.noop),
    ]
