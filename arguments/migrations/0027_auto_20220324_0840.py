# Generated by Django 2.2 on 2022-03-24 08:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('arguments', '0026_auto_20220317_0921'),
    ]

    operations = [
        migrations.AlterField(
            model_name='argumentreport',
            name='remark',
            field=models.CharField(max_length=1000, null=True),
        ),
    ]
