from google.oauth2 import service_account

from .base import *

ALLOWED_HOSTS = [
    '*'
]

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

CORS_ORIGIN_WHITELIST = [
    'http://localhost:4200',
    'http://192.168.1.106:4200',
]

DOMAIN_NAME = 'localhost:4200'

ADMINS = [
    ('Admin', 'admin@moogter.com'),
]

# Send email to the console for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
