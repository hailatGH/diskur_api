# Generated by Django 2.1.3 on 2019-05-25 04:50

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_following'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='following',
            name='followee',
        ),
        migrations.RemoveField(
            model_name='following',
            name='follower',
        ),
        migrations.AddField(
            model_name='moogtmedauser',
            name='follower',
            field=models.ManyToManyField(related_name='followings', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='moogtmedauser',
            name='following',
            field=models.ManyToManyField(related_name='followers', to=settings.AUTH_USER_MODEL),
        ),
        migrations.DeleteModel(
            name='Following',
        ),
    ]
