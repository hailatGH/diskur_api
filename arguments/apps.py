from django.apps import AppConfig


class ArgumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arguments'

    def ready(self):
        import arguments.signals  # noqa
