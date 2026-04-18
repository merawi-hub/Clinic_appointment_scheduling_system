from django.db import migrations, models
import django.db.models.deletion
import random
import string
from datetime import date


def populate_refs(apps, schema_editor):
    Appointment = apps.get_model('core', 'Appointment')
    used = set()
    for appt in Appointment.objects.all():
        while True:
            ref = f"AC-{date.today().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
            if ref not in used:
                used.add(ref)
                break
        appt.appointment_ref = ref
        appt.save(update_fields=['appointment_ref'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_leave_request'),
    ]

    operations = [
        # Add without unique first
        migrations.AddField(
            model_name='appointment',
            name='appointment_ref',
            field=models.CharField(blank=True, max_length=20, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='appointment',
            name='patient_email',
            field=models.EmailField(blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='appointment',
            name='patient_phone',
            field=models.CharField(blank=True, max_length=15, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='appointment',
            name='follow_up_of',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='follow_ups',
                to='core.appointment'
            ),
        ),
        # Populate existing rows with unique refs
        migrations.RunPython(populate_refs, migrations.RunPython.noop),
        # Now add unique constraint
        migrations.AlterField(
            model_name='appointment',
            name='appointment_ref',
            field=models.CharField(blank=True, max_length=20, unique=True),
        ),
    ]
