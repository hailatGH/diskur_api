# Generated by Django 2.2 on 2021-03-19 13:14

import annoying.fields
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('arguments', '0018_auto_20210301_1203'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArgumentScore',
            fields=[
                ('score_now', models.DecimalField(decimal_places=2, default=0, max_digits=11)),
                ('score_before', models.DecimalField(decimal_places=2, default=0, max_digits=11)),
                ('score_last_updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('overall_score', models.DecimalField(decimal_places=2, default=0, max_digits=11)),
                ('argument', annoying.fields.AutoOneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='score', serialize=False, to='arguments.Argument')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
