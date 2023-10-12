from django.apps import AppConfig


class MoogtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'moogts'

    def ready(self):
        import moogts.signals  # noqa
