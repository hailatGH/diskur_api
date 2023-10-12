from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from api.utils import get_admin_url

from meda.admin import ReportModelAdmin
from users.serializers import AccountReportSerializer, MoogtMedaUserSerializer

from .forms import MoogtMedaSignupForm
from .models import AccountReport, MoogtMedaUser, Profile, Activity, CreditPoint


class MoogtMedaUserAdmin(UserAdmin):
    """A custom user admin for MoogtMeda."""
    model = MoogtMedaUser
    add_form = MoogtMedaSignupForm


class ProfileAdmin(admin.ModelAdmin):
    model = Profile


class AccountReportAdmin(ReportModelAdmin):
    list_display = ReportModelAdmin.list_display + ('user',)
    list_filter = ReportModelAdmin.list_filter + ('user', )
    exclude = ('user', )
    readonly_fields = ReportModelAdmin.readonly_fields + ('get_user', )
    
    def get_user(self, obj):
        return format_html(f'<a href="{get_admin_url(obj.user)}">{obj.user}</a>')
    get_user.short_description = 'User'

    def delete_item(self, report):
        report.user.delete()
        
    def get_notification_data(self, report):
        return {
            'report': AccountReportSerializer(report).data,
            'user': MoogtMedaUserSerializer(report.user).data
        }


admin.site.register(MoogtMedaUser, MoogtMedaUserAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Activity)
admin.site.register(CreditPoint)
admin.site.register(AccountReport, AccountReportAdmin)
