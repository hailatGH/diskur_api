from django.core.management.base import BaseCommand, CommandError
from os import system
import _thread
import time


class Command(BaseCommand):
    help = 'Starts a local server connected to the Google Cloud production database.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "Starting the Google Cloud SQL Proxy..."))
        _thread.start_new_thread(system,
                                 ('./cloud_sql_proxy -instances=moogtmeda:us-central1:moogtmeda-instance=tcp:3306',))
        time.sleep(2)  # Wait for proxy to start.
        self.stdout.write(self.style.WARNING(
            "Starting the local server with the production database..."))
        system('MOOGTMEDA_USE_PROD_DB="true" python manage.py runserver')
