import _thread
import time
from django.core.management.base import BaseCommand, CommandError
from os import system


class Command(BaseCommand):
    help = 'Runs the migrate command on the production database. '

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "Starting the Google Cloud SQL Proxy..."))
        _thread.start_new_thread(system,
                                 ('../cloud_sql_proxy -instances=moogter-backend-dev:us-central1:moogter-dev-instance=tcp:3306',))
        time_wait = 30
        self.stdout.write(self.style.WARNING(
            "Waiting " + str(time_wait) + " seconds for the proxy to start..."))
        time.sleep(time_wait)  # Wait for proxy to start.
        self.stdout.write(self.style.WARNING(
            "Applying migrations to production database..."))
        system('MOOGTMEDA_USE_PROD_DB="true" python manage.py migrate')

        self.stdout.write(self.style.WARNING(
            "Killing the Google Cloud SQL Proxy..."))
        system('killall cloud_sql_proxy')

        self.stdout.write(self.style.SUCCESS(
            "Successfully migrated production database."))
