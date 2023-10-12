import json
import pytz

from collections import OrderedDict, namedtuple
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from rest_framework.pagination import BasePagination, CursorPagination, _reverse_ordering
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param
from rest_framework.settings import api_settings


class CustomCursorPagination(BasePagination):

    def has_prev(self, cursor_date):
        if not cursor_date:
            return False
        return self.queryset.filter(created_at__lt=cursor_date).count() > self.page_size

    def has_next(self, cursor_date):
        if not cursor_date:
            return False
        return self.queryset.filter(created_at__gt=cursor_date).exists()

    def next_cursor(self, cursor_date):
        if self.has_next(cursor_date):
            qs = self.queryset \
                .filter(created_at__gt=cursor_date) \
                .order_by(self.datetime_field)[:self.page_size]
            return getattr(qs[len(qs) - 1], self.datetime_field)

    def prev_cursor(self, cursor_date):
        if self.has_prev(cursor_date):
            qs = self.queryset \
                .filter(created_at__lte=cursor_date) \
                .order_by('-' + self.datetime_field)[:self.page_size + 1]
            last_idx = len(qs) - 1

            return getattr(qs[last_idx], self.datetime_field)

    def get_next_link(self):
        if self.after_date:
            # find next next cursor
            next_cursor = self.next_cursor(self.get_datetime_obj(self.after_date))
            next_cursor = self.next_cursor(next_cursor)
        elif self.before_date:
            # find next cursor
            next_cursor = self.next_cursor(self.get_datetime_obj(self.before_date))

        if next_cursor:
            next_cursor = next_cursor.timestamp()
            self.base_url = remove_query_param(self.base_url, 'after')
            return replace_query_param(self.base_url, 'before', str(next_cursor))

    def get_prev_link(self):
        if self.after_date:
            # return curr cursor
            prev_cursor = self.get_datetime_obj(self.after_date)
        elif self.before_date:
            # find prev cursor
            prev_cursor = self.prev_cursor(self.get_datetime_obj(self.before_date))

        if prev_cursor:
            prev_cursor = prev_cursor.timestamp()
            self.base_url = remove_query_param(self.base_url, 'after')
            return replace_query_param(self.base_url, 'before', str(prev_cursor))

    @staticmethod
    def get_datetime_obj(timestamp):
        return datetime.fromtimestamp(timestamp, tz=pytz.timezone(settings.TIME_ZONE))

    def get_count(self, queryset):
        """
        Determine an object count, supporting either querysets or regular lists.
        """
        return queryset.count()

    def get_after_results(self, queryset, cursor_date, page_size):
        # after doesn't include the cursor date passed when filtering
        return queryset.filter(**{f'{self.datetime_field}__gt': cursor_date}).order_by(self.datetime_field)[:page_size]

    def get_before_results(self, queryset, cursor_date, page_size):
        # before includes the cursor date itself when filtering
        return queryset.filter(**{f'{self.datetime_field}__lte': cursor_date}).order_by('-' + self.datetime_field)[:page_size]

    def paginate_queryset(self, queryset, request, view=None):
        self.base_url = request.build_absolute_uri()
        self.count = self.get_count(queryset)
        self.queryset = queryset

        self.page_size = int(request.query_params.get('limit', api_settings.PAGE_SIZE))
        self.after_date = json.loads(request.query_params.get('after', 'null'))
        self.before_date = json.loads(request.query_params.get('before', 'null'))
        self.datetime_field = 'sort_date'

        if not self.before_date and not self.after_date:
            self.before_date = timezone.now().timestamp()

        if self.after_date:
            queryset = self.get_after_results(queryset,
                                              self.get_datetime_obj(self.after_date),
                                              self.page_size)
        elif self.before_date:
            queryset = self.get_before_results(queryset,
                                               self.get_datetime_obj(self.before_date),
                                               self.page_size)
        else:
            raise ValidationError("You have to have either 'after' or 'before' query parameter in the request")

        self.page = queryset
        return self.page

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.count),
            ('next', self.get_next_link()),
            ('prev', self.get_prev_link()),
            ('results', data)
        ]))

class ArgumentListPagination(CursorPagination):
    def paginate_queryset(self, queryset, request, view=None, offset=0):
        self.page_size = self.get_page_size(request)
        if not self.page_size:
            return None

        self.base_url = request.build_absolute_uri()
        self.ordering = self.get_ordering(request, queryset, view)

        self.cursor = self.decode_cursor(request)
        if self.cursor is None:
            (offset, reverse, current_position) = (offset, False, None)
        else:
            (offset, reverse, current_position) = self.cursor

        # Cursor pagination always enforces an ordering.
        if reverse:
            queryset = queryset.order_by(*_reverse_ordering(self.ordering))
        else:
            queryset = queryset.order_by(*self.ordering)

        # If we have a cursor with a fixed position then filter by that.
        if current_position is not None:
            order = self.ordering[0]
            is_reversed = order.startswith('-')
            order_attr = order.lstrip('-')

            # Test for: (cursor reversed) XOR (queryset reversed)
            if self.cursor.reverse != is_reversed:
                kwargs = {order_attr + '__lt': current_position}
            else:
                kwargs = {order_attr + '__gt': current_position}

            queryset = queryset.filter(**kwargs)

        # If we have an offset cursor then offset the entire page by that amount.
        # We also always fetch an extra item in order to determine if there is a
        # page following on from this one.
        results = list(queryset[offset:offset + self.page_size + 1])
        self.page = list(results[:self.page_size])

        # Determine the position of the final item following the page.
        if len(results) > len(self.page):
            has_following_position = True
            following_position = self._get_position_from_instance(results[-1], self.ordering)
        else:
            has_following_position = False
            following_position = None

        if reverse:
            # If we have a reverse queryset, then the query ordering was in reverse
            # so we need to reverse the items again before returning them to the user.
            self.page = list(reversed(self.page))

            # Determine next and previous positions for reverse cursors.
            self.has_next = (current_position is not None) or (offset > 0)
            self.has_previous = has_following_position
            if self.has_next:
                self.next_position = current_position
            if self.has_previous:
                self.previous_position = following_position
        else:
            # Determine next and previous positions for forward cursors.
            self.has_next = has_following_position
            self.has_previous = (current_position is not None) or (offset > 0)
            if self.has_next:
                self.next_position = following_position
            if self.has_previous:
                self.previous_position = current_position

        # Display page controls in the browsable API if there is more
        # than one page.
        if (self.has_previous or self.has_next) and self.template is not None:
            self.display_page_controls = True

        return self.page