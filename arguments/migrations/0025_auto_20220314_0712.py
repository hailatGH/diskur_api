# Generated by Django 2.2 on 2022-03-14 07:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('arguments', '0024_argumentreport'),
    ]

    operations = [
        migrations.AlterField(
            model_name='argumentreport',
            name='argument',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='arguments.Argument'),
        ),
    ]
