from django.contrib import admin
from django.utils.html import format_html
from api.utils import get_admin_url

from meda.admin import NullListFilter, ReportModelAdmin
from views.models import View, ViewReport, ViewStats
from views.serializers import ViewNotificationSerializer, ViewReportSerializer


class ContentNullListFilter(NullListFilter):
    title = u'Content'
    parameter_name = u'content'


class ViewAdmin(admin.ModelAdmin):
    '''Admin View for View'''

    list_display = ['content', 'user', 'type',
                    'reaction_type', 'created_at', 'is_hidden', 'is_draft']
    list_filter = [ContentNullListFilter, 'type', 'reaction_type', 'is_draft']
    search_fields = ['content', 'user']
    ordering = ['created_at', ]


class ViewReportAdmin(ReportModelAdmin):
    list_display = ReportModelAdmin.list_display + ('view',)
    list_filter = ReportModelAdmin.list_filter + ('view__user', 'view',)
    exclude = ('view', )
    readonly_fields = ReportModelAdmin.readonly_fields + ('get_view',)
    
    def get_view(self, obj):
        return format_html(f'<a href="{get_admin_url(obj.view)}">{obj.view}</a>')
    get_view.short_description = 'View'
    
    def delete_item(self, report):
        report.view.delete()
        
    def get_notification_data(self, report):
        return {
            'report': ViewReportSerializer(report).data,
            'view': ViewNotificationSerializer(report.view).data
        }

admin.site.register(View, ViewAdmin)
admin.site.register(ViewReport, ViewReportAdmin)
admin.site.register(ViewStats)
