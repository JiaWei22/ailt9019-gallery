from django.db import migrations, models


def assign_numbers(apps, schema_editor):
    Event = apps.get_model('showcase', 'Event')
    Project = apps.get_model('showcase', 'Project')
    alias = schema_editor.connection.alias
    for event in Event.objects.using(alias).all().iterator():
        count = 0
        for count, pk in enumerate(Project.objects.using(alias).filter(event=event).order_by('pk').values_list('pk', flat=True), 1):
            Project.objects.using(alias).filter(pk=pk).update(number=count)
        Event.objects.using(alias).filter(pk=event.pk).update(project_counter=count)


class Migration(migrations.Migration):
    dependencies = [('showcase', '0011_projectdetails_demo_checked_at_and_more')]
    operations = [
        migrations.AddField(model_name='event', name='project_counter', field=models.PositiveIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='project', name='number', field=models.PositiveIntegerField(null=True, editable=False)),
        migrations.RunPython(assign_numbers, migrations.RunPython.noop),
        migrations.AlterField(model_name='project', name='number', field=models.PositiveIntegerField(editable=False)),
        migrations.AddConstraint(model_name='project', constraint=models.UniqueConstraint(fields=['event','number'], name='w13_project_number')),
    ]
