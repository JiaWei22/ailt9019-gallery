from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0002_coursestaff_alter_student_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="counted",
            field=models.BooleanField(default=True),
        ),
    ]
