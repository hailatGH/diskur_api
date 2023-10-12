from django.contrib import admin
from django.utils.html import format_html
from api.utils import get_admin_url

from moogts.serializers import MoogtNotificationSerializer, MoogtReportSerializer

from .models import MoogtMiniSuggestion, MoogtBanner, Donation, Moogt, MoogtReport
from meda.admin import NullListFilter, ReportModelAdmin


class OppositionNullListFilter(NullListFilter):
    title = u'Opposition'
    parameter_name = u'opposition'


class MoogtAdmin(admin.ModelAdmin):
    '''Admin View for Moogt'''

    list_display = ['resolution', 'proposition',
                    'opposition', 'started_at', 'has_ended', 'is_paused']
    list_filter = [OppositionNullListFilter, 'has_ended', 'is_paused']
    ordering = ['started_at', ]
    search_fields = ['resolution', ]


class MoogtReportAdmin(ReportModelAdmin):
    list_display = ReportModelAdmin.list_display + \
        ('moogt', 'proposition', 'opposition', 'moderator')
    list_filter = ReportModelAdmin.list_filter + ('moogt',)
    exclude = ('moogt',)
    readonly_fields = ReportModelAdmin.readonly_fields + ('get_moogt', )

    def get_moogt(self, obj):
        return format_html(f'<a href="{get_admin_url(obj.moogt)}">{obj.moogt}</a>')
    get_moogt.short_description = 'Moogt'

    def proposition(self, obj):
        return obj.moogt.proposition

    def opposition(self, obj):
        return obj.moogt.opposition

    def moderator(self, obj):
        return obj.moogt.moderator

    def delete_item(self, report):
        report.moogt.delete()

    def get_notification_data(self, report):
        return {
            'report': MoogtReportSerializer(report).data,
            'moogt': MoogtNotificationSerializer(report.moogt).data
        }


admin.site.register(Moogt, MoogtAdmin)
admin.site.register(MoogtMiniSuggestion)
admin.site.register(MoogtBanner)
admin.site.register(Donation)
admin.site.register(MoogtReport, MoogtReportAdmin)
