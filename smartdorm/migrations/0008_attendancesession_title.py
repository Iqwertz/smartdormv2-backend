from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smartdorm', '0007_event_attendancesession_attendancerecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancesession',
            name='title',
            field=models.CharField(blank=True, default='', help_text='Optional custom session name', max_length=255),
        ),
    ]