from django.utils.safestring import mark_safe
from django.urls import reverse

from django import template
register = template.Library()


@register.simple_tag
def moogter_user_display(user):
    return mark_safe("<a class='mgt-username' href='%s'>&#64%s</a>"
                     % (reverse('users:anonymous_profile', args=[user.username]), user.username))


@register.inclusion_tag('users/_engagements.html')
def engagements_display(credit_points_count):
    points_count = {}

    for c in credit_points_count:
        points_count[c['type']] = c['type__count']

    return points_count

