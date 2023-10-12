# Generated by Django 2.2 on 2022-03-10 08:50

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('views', '0007_remove_view_banner'),
    ]

    operations = [
        migrations.CreateModel(
            name='ViewReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('link', models.URLField(blank=True, default=None, max_length=1000, null=True)),
                ('reason', models.CharField(max_length=200)),
                ('reported_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('view', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='views.View')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
