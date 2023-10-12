# Generated by Django 2.2 on 2021-04-26 12:37

from django.db import migrations
from moogts.models import MoogtActivityType
from meda.enums import ActivityStatus

def update_moogt_activity(apps, schema_editor):
    # update moogt activities 
    MoogtActivity = apps.get_model('moogts', 'MoogtActivity')

    MoogtActivity.objects \
        .filter(type=MoogtActivityType.ENDORSEMENT.name) \
        .update(status=ActivityStatus.ACCEPTED.name)
        
    MoogtActivity.objects \
        .filter(type=MoogtActivityType.DISAGREEMENT.name) \
        .update(status=ActivityStatus.ACCEPTED.name)

class Migration(migrations.Migration):

    dependencies = [
        ('moogts', '0031_moogtactivity_react_to'),
    ]

    operations = [
        migrations.RunPython(update_moogt_activity)
    ]
