from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0007_review_suggestions"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewevent",
            name="lock_reason",
            field=models.TextField(blank=True),
        ),
    ]
