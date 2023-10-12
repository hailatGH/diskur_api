from .base import *

# We might be making lot's of change to the REST_FRAMEWORK settings, but
# we don't want that to break our tests, that's why we are
# redefining some of those settings
# use: python manage.py testall for testing or if you want to test the api app alone
# use: python manage.py test api --settings api.tests.settings
DATABASES = {
    # When running locally, use a local sqlite3 database for testing.
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'moogtmeda.db'),
    },
}

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,

    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

DJANGO_NOTIFICATIONS_CONFIG = {
    'USE_JSONFIELD': True,
}
