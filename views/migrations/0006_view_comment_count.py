# Generated by Django 2.2 on 2020-08-22 06:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('views', '0005_merge_20200803_0857'),
    ]

    operations = [
        migrations.AddField(
            model_name='view',
            name='comment_count',
            field=models.IntegerField(default=0),
        ),
    ]
