# Generated by Django 2.2 on 2020-10-19 13:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0009_auto_20201005_1328'),
    ]

    operations = [
        migrations.AddField(
            model_name='regularmessage',
            name='is_reply',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='regularmessage',
            name='reply_to_invitation_message',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='chat.InvitationMessage'),
        ),
        migrations.AddField(
            model_name='regularmessage',
            name='reply_to_mini_suggestion_message',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='chat.MiniSuggestionMessage'),
        ),
        migrations.AddField(
            model_name='regularmessage',
            name='reply_to_regular_message',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='chat.RegularMessage'),
        ),
    ]
