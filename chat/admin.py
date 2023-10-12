from django.contrib import admin

# Register your models here.
from chat.models import Conversation, InvitationMessage, RegularMessage, MiniSuggestionMessage
from chat.models import Conversation, InvitationMessage, RegularMessage, MessageSummary, ModeratorInvitationMessage

admin.site.register(Conversation)
admin.site.register(InvitationMessage)
admin.site.register(RegularMessage)
admin.site.register(MiniSuggestionMessage)
admin.site.register(ModeratorInvitationMessage)
admin.site.register(MessageSummary)
