from django.contrib import admin
from meda.admin import ReportModelAdmin

from polls.models import Poll, PollReport
from polls.serializers import PollNotificationSerializer, PollReportSerializer


class PollsAdmin(admin.ModelAdmin):
    '''Admin View for Polls'''

    list_display = ['title', 'user', 'start_date', 'end_date', 'is_closed']
    list_filter = ['is_closed']
    search_fields = ['title', ]
    ordering = ['start_date', ]


class PollReportAdmin(ReportModelAdmin):
    list_display = ReportModelAdmin.list_display + ('poll',)
    list_filter = ReportModelAdmin.list_filter + ('poll', 'poll__user', )

    def delete_item(self, report):
        report.poll.delete()
        
    def get_notification_data(self, report):
        return {
            'report': PollReportSerializer(report).data,
            'poll': PollNotificationSerializer(report.poll).data
        }


admin.site.register(Poll, PollsAdmin)
admin.site.register(PollReport, PollReportAdmin)
