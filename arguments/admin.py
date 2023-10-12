from django.contrib import admin
from django.utils.html import format_html
from api.utils import get_admin_url

from arguments.models import Argument, ArgumentReport
from arguments.serializers import ArgumentNotificationSerializer, ArgumentReportSerializer
from meda.admin import ReportModelAdmin


class ArgumentReportAdmin(ReportModelAdmin):
    list_display = ReportModelAdmin.list_display + ('argument',)
    list_filter = ReportModelAdmin.list_filter + \
        ('argument__user', 'argument',)
    exclude = ('argument', )
    readonly_fields = ReportModelAdmin.readonly_fields + ('get_argument', )
    
    def get_argument(self, obj):
        return format_html(f'<a href="{get_admin_url(obj.argument)}">{obj.argument}</a>')
    get_argument.short_description = 'Argument'
    
    def delete_item(self, report):
        report.argument.delete()
        
    def get_notification_data(self, report):
        return {
            'report': ArgumentReportSerializer(report).data,
            'argument': ArgumentNotificationSerializer(report.argument).data
        }


admin.site.register(Argument)
admin.site.register(ArgumentReport, ArgumentReportAdmin)
