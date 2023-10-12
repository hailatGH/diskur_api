# Generated by Django 2.2 on 2020-06-10 12:45

import annoying.fields
import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('api', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Moogt',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('resolution', models.CharField(max_length=200)),
                ('description', models.CharField(blank=True, max_length=560, null=True)),
                ('next_turn_proposition', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('has_ended', models.BooleanField(default=False)),
                ('end_requested', models.BooleanField(default=False)),
                ('end_requested_by_proposition', models.BooleanField(default=False)),
                ('is_premiering', models.BooleanField(default=False)),
                ('premiering_duration', models.DurationField(default=None, null=True)),
                ('end_request_status', models.CharField(choices=[('CNCD', 'Concede'), ('DSGR', 'Disagree')], default=None, max_length=4, null=True)),
                ('visibility', models.CharField(choices=[('PUBLIC', 'To the public'), ('FOLLOWERS_ONLY', 'To my subscribers only')], default='PUBLIC', max_length=15)),
                ('type', models.CharField(choices=[('DUO', 'Duo Moogt'), ('GROUP', 'Group Moogt')], default='DUO', max_length=56)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('latest_argument_added_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('max_duration', models.DurationField(default=datetime.timedelta(days=365))),
                ('idle_timeout_duration', models.DurationField(default=datetime.timedelta(seconds=3600))),
                ('thumbnail', models.ImageField(upload_to='')),
                ('moderator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderating_moogts', to=settings.AUTH_USER_MODEL)),
                ('opposition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opposition_moogts', to=settings.AUTH_USER_MODEL)),
                ('proposition', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='proposition_moogts', to=settings.AUTH_USER_MODEL)),
                ('tags', models.ManyToManyField(blank=True, to='api.Tag')),
            ],
        ),
        migrations.CreateModel(
            name='MoogtGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('users', models.ManyToManyField(related_name='moogt_groups', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MoogtScore',
            fields=[
                ('score_now', models.DecimalField(decimal_places=2, default=0, max_digits=11)),
                ('score_before', models.DecimalField(decimal_places=2, default=0, max_digits=11)),
                ('score_last_updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('moogt', annoying.fields.AutoOneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='score', serialize=False, to='moogts.Moogt')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MoogtStats',
            fields=[
                ('moogt', annoying.fields.AutoOneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='stats', serialize=False, to='moogts.Moogt')),
                ('view_count', models.IntegerField(default=0)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MoogtParticipant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('moogt_group', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='moogts.MoogtGroup')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moogt_participant', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
