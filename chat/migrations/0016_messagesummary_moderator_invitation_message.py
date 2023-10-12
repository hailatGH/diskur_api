# Generated by Django 2.2 on 2022-01-17 11:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0015_moderatorinvitationmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='messagesummary',
            name='moderator_invitation_message',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='summaries', to='chat.ModeratorInvitationMessage'),
        ),
    ]
