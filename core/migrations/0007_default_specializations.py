from django.db import migrations

DEFAULT_SPECIALIZATIONS = [
    'General Practice',
    'Cardiology',
    'Dermatology',
    'Neurology',
    'Orthopedics',
    'Pediatrics',
    'Gynecology',
    'Ophthalmology',
    'ENT (Ear, Nose & Throat)',
    'Psychiatry',
    'Oncology',
    'Urology',
    'Endocrinology',
    'Gastroenterology',
    'Pulmonology',
    'Nephrology',
    'Rheumatology',
    'Dentistry',
    'Emergency Medicine',
    'Surgery',
]


def add_specializations(apps, schema_editor):
    Specialization = apps.get_model('core', 'Specialization')
    for name in DEFAULT_SPECIALIZATIONS:
        Specialization.objects.get_or_create(name=name)


def remove_specializations(apps, schema_editor):
    Specialization = apps.get_model('core', 'Specialization')
    Specialization.objects.filter(name__in=DEFAULT_SPECIALIZATIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_profilechangerequest_new_password_and_more'),
    ]
    operations = [
        migrations.RunPython(add_specializations, remove_specializations),
    ]
