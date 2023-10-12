from django.contrib import admin
from django.contrib.admin import SimpleListFilter

from meda.models import BaseReport
from notifications.enums import NOTIFICATION_TYPES
from notifications.models import Notification
from notifications.signals import notify


class NullListFilter(SimpleListFilter):
    """Filters the null value of a field """

    def lookups(self, request, model_admin):
        return(
            ('1', 'Null', ),
            ('0', 'Not Null', ),
        )

    def queryset(self, request, queryset):
        if self.value() in ('0', '1'):
            kwargs = {'{0}__isnull'.format(
                self.parameter_name): self.value() == '1'}
            return queryset.filter(**kwargs)

        return queryset


class ReportModelAdmin(admin.ModelAdmin):
    date_hierarchy = 'created_at'
    list_display = ('reason', 'created_at', 'updated_at', 'reported_by',
                    'reported_on', 'status', 'link', 'action_taken_by', 'remark',)
    list_filter = ('created_at', 'reported_by', 'status',)
    readonly_fields = ('reason', 'updated_at', 'reported_by', 'status', 'link', 'action_taken_by')

    def reported_on(self, obj):
        return obj.reported_on()

    def render_change_form(self, request, context, *args, **kwargs):
        is_report_pending = context['original'].status == BaseReport.PENDING
        context.update({'show_deactivate_account': is_report_pending})
        context.update({'show_delete_item': is_report_pending})
        context.update({'show_warn_user': is_report_pending})

        return super().render_change_form(request, context, *args, **kwargs)

    def response_post_save_change(self, request, obj):
        if '_deactivateaccount' in request.POST:
            obj.status = BaseReport.ACCOUNT_DEACTIVATED
            obj.action_taken_by = request.user
            obj.save()
            user = obj.reported_on()
            user.active = False
            user.save()
        if '_deleteitem' in request.POST:
            obj.status = BaseReport.ITEM_DELETED
            obj.action_taken_by = request.user
            obj.save()
            self.delete_item(obj)

        if '_warnuser' in request.POST:
            obj.status = BaseReport.USER_WARNED
            obj.action_taken_by = request.user
            obj.save()
            notify.send(recipient=obj.reported_on(),
                        sender=request.user,
                        verb='warned',
                        send_email=True,
                        send_telegram=True,
                        data=self.get_notification_data(obj),
                        type=NOTIFICATION_TYPES.user_warned,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=obj,
                        push_notification_title='Warning',
                        push_notification_description='You received warning notification',)

        return super().response_post_save_change(request, obj)

    def delete_item(self, report):
        pass
    
    def get_notification_data(self, report):
        pass
