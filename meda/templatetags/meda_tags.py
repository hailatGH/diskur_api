from django import template
register = template.Library()


@register.inclusion_tag('meda/_nav_bar.html')
def nav_bar(user):
    return {'user': user}


@register.inclusion_tag('meda/_moogt_card.html')
def moogt_card(moogt):
    return {'moogt': moogt}


@register.inclusion_tag('meda/_argument_card.html')
def argument_card(argument, user):
    disallow_voting = False
    if not user.is_authenticated:
        disallow_voting = True
    elif user == argument.moogt.proposition or user == argument.moogt.opposition:
        disallow_voting = True

    return {'argument': argument, 'user': user, 'disallow_voting': disallow_voting}


@register.inclusion_tag('meda/_side_pane.html')
def side_pane(user):
    return {'user': user}


@register.inclusion_tag('meda/_invitation_modal.html')
def invitation_modal(moogt):
    return {'moogt': moogt}


@register.inclusion_tag('meda/_argument_input_card.html')
def argument_input_card(argument_form, moogt):
    return {'argument_form': argument_form, 'moogt': moogt}

@register.inclusion_tag('meda/_comment_card.html')
def comment_card(user, comment):
    return {'user': user, 'comment': comment}
