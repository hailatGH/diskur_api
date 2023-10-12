from django.apps import AppConfig


class ViewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'views'

    def ready(self):
        import views.signals  # noqa
