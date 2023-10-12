# Generated by Django 4.2.5 on 2023-09-22 09:02

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('arguments', '0028_argumentactivityaction'),
    ]

    operations = [
        migrations.AlterField(
            model_name='argumentstats',
            name='applauds',
            field=models.ManyToManyField(related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='argumentstats',
            name='downvotes',
            field=models.ManyToManyField(related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='argumentstats',
            name='upvotes',
            field=models.ManyToManyField(related_name='+', to=settings.AUTH_USER_MODEL),
        ),
    ]
