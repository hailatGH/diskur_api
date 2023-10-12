from google.oauth2 import service_account

from .base import *

DATABASES = {
    # This overrides the database configuration to use the production database
    # on the Google Cloud SQL service via the local proxy.
    # To start the proxy via command line:
    #
    #     $ cloud_sql_proxy -instances=[INSTANCE_CONNECTION_NAME]=tcp:3306
    #
    # See https://cloud.google.com/sql/docs/mysql-connect-proxy
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'HOST': '127.0.0.1',
        'PORT': '5432',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
    }
}

GS_BUCKET_NAME = 'moogter-dev-storage'
GS_PROJECT_ID = 'moogter-backend-dev'

GS_CREDENTIALS = service_account.Credentials.from_service_account_file('/tmp/key-file.json')

STATICFILES_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
