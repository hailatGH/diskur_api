from drf_multiple_model.pagination import MultipleModelLimitOffsetPagination
from rest_framework.pagination import LimitOffsetPagination


class LargeResultsSetPagination(LimitOffsetPagination):
    default_limit = 1000


class StandardResultsSetPagination(LimitOffsetPagination):
    default_limit = 100


class SmallResultsSetPagination(LimitOffsetPagination):
    default_limit = 10


class MultiModelLimitOffsetPagination(MultipleModelLimitOffsetPagination):
    default_limit = 3
