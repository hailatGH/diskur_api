# Imports the Google Cloud client library
import environ
import io
import google.cloud.logging

from .base import *
from google.cloud import secretmanager

# [START gaeflex_py_django_secret_config]
env = environ.Env(DEBUG=(bool, False))

# Pull secrets from Secret Manager
project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")

client = secretmanager.SecretManagerServiceClient()
settings_name = os.environ.get("SETTINGS_NAME", "django_settings")
name = f"projects/{project_id}/secrets/{settings_name}/versions/latest"
payload = client.access_secret_version(name=name).payload.data.decode("UTF-8")

env.read_env(io.StringIO(payload))
# [END gaeflex_py_django_secret_config]

SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
# Change this to "False" when you are ready for production
DEBUG = env("DEBUG")

# Special setting.
DOMAIN_NAME = "dev.frontend.moogter.com"

ALLOWED_HOSTS += ['moogter-backend-dev.oa.r.appspot.com']

# [START dbconfig]
# [START gaeflex_py_django_database_config]
# Use django-environ to parse the connection string
DATABASES = {"default": env.db()}
# [END gaeflex_py_django_database_config]
# [END dbconfig]

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            # "hosts": [('10.224.55.35', 6379)], Change back to google when scaling in the future
            "hosts": [('redis://:abFVOjZZymtA5WrBviNJ6Ov7DkN7zNkM@redis-10088.c250.eu-central-1-1.ec2.cloud.redislabs.com:10088')],
        },
    },
}

# Static files (CSS, JavaScript, Images)
# [START staticurl]
# [START gaeflex_py_django_static_config]
# Define static storage via django-storages[google]
GS_BUCKET_NAME = env("GS_BUCKET_NAME")
GS_PROJECT_ID = project_id
DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
STATICFILES_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"

STATIC_URL = f'https://storage.googleapis.com/${GS_BUCKET_NAME}/static/'
GS_DEFAULT_ACL = "publicRead"
GS_FILE_OVERWRITE = False
# [END gaeflex_py_django_static_config]
# [END staticurl]

ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# Instantiates a client
client = google.cloud.logging.Client()

# Retrieves a Cloud Logging handler based on the environment
# you're running in and integrates the handler with the
# Python logging module. By default this captures all logs
# at INFO level and higher
client.setup_logging()

CORS_ORIGIN_WHITELIST = [
    'https://moogter.com',
    'https://dev.frontend.moogter.com',
    'https://api.telegram.org',
    'http://localhost:4200',
    'http://moogter.feuzion.com/',
    'https://moogter.feuzion.com/',
]

ADMINS = [
    ('MoogterHimself', 'moogter@bete-semay.com'),
]
