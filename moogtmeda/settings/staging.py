# Imports the Google Cloud client library
import google.cloud.logging
from google.oauth2 import service_account

from .base import *

# Special setting.
DOMAIN_NAME = "staging.frontend.moogter.com"

ALLOWED_HOSTS += ['moogter-backend-staging.ew.r.appspot.com']

# TODO: Disable debug mode in production.
# DO NOT LAUNCH TO PUBLIC WITH DEBUG TRUE.
DEBUG = False

# Use production database.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': '/cloudsql/moogter-backend-staging:europe-west1:moogter-staging-instance',
        'USER': 'moogter-staging-user',
        'PASSWORD': '4uFFDc6IhaPtj0qD',
        'NAME': 'moogter_staging',
        'OPTIONS': {'charset': 'utf8mb4'}
    }
}

# TODO(genoishelo): Change and replace GCP credentials with env variable.
# django-storages settings
DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
GS_BUCKET_NAME = 'moogter-dev-staging'
GS_PROJECT_ID = 'moogter-backend-staging'

GS_DEFAULT_ACL = 'publicRead'

ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# Instantiates a client
client = google.cloud.logging.Client()

# Connects the logger to the root logging handler; by default this captures
# all logs at INFO level and higher
client.setup_logging()

CORS_ORIGIN_WHITELIST = [
    'https://staging.frontend.moogter.com',
    'http://staging.frontend.moogter.com',
]
