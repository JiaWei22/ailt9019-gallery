from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0006_event_rubric_preview"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="suggestions",
            field=models.TextField(blank=True),
        ),
    ]
