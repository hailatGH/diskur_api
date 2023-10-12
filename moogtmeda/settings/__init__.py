import os

# https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
GAE_ENV_KEY = 'GOOGLE_CLOUD_PROJECT'
DEV_APPLICATION_ID = 'moogter-backend-dev'
STAGING_APPLICATION_ID = 'moogter-backend-staging'
PROD_APPLICATION_ID = 'moogter-backend-prod'

if os.getenv(GAE_ENV_KEY, None) == DEV_APPLICATION_ID:
    from .development import *
elif os.getenv(GAE_ENV_KEY, None) == STAGING_APPLICATION_ID:
    from .staging import *
elif os.getenv(GAE_ENV_KEY, None) == PROD_APPLICATION_ID:
    from .production import *
else:
    from .local import *
