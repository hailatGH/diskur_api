# Generated by Django 2.2 on 2021-02-16 12:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moogts', '0024_readby'),
    ]

    operations = [
        migrations.AlterField(
            model_name='moogtactivity',
            name='status',
            field=models.CharField(choices=[('Pending', 'PENDING'), ('Accepted', 'ACCEPTED'), ('Declined', 'DECLINED'), ('Expired', 'EXPIRED')], default='Pending', max_length=15),
        ),
    ]
