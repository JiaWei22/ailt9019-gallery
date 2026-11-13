from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0004_revieweridentity_activation"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="issued_password",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="student",
            name="password",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
