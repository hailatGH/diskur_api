from chat.models import MiniSuggestionMessage
from meda.tests.test_models import create_moogt
from moogts.models import MoogtMiniSuggestion


def create_mini_suggestion_message(conversation, user):
    moogt = create_moogt(resolution='test resolution')
    moogt.set_proposition(user)
    mini_suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt)
    mini_suggestion_message = MiniSuggestionMessage.objects.create(conversation=conversation,
                                                                   mini_suggestion=mini_suggestion)
    return mini_suggestion_message
