# Generated by Django 2.2 on 2020-10-22 07:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0009_auto_20201005_1328'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitationmessage',
            name='is_removed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='minisuggestionmessage',
            name='is_removed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='regularmessage',
            name='is_removed',
            field=models.BooleanField(default=False),
        ),
    ]
