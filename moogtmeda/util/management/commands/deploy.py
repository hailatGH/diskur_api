from django.core.management.base import BaseCommand, CommandError
from os import system
import _thread
import time


class Command(BaseCommand):
    help = 'Prepares and deploys the current state of the application to gcloud.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Migrating prodution database."))
        res = system('python manage.py migrateprod')
        if res:
            raise CommandError('Failed to apply database migrations.')

        self.stdout.write(self.style.WARNING("Clearing 'static/' directory."))
        res = system('rm -rf static/')
        if res:
            raise CommandError('Cannot delete static/ directory.')

        self.stdout.write(self.style.WARNING("Clearing 'lib/' directory."))
        res = system('rm -rf lib/')
        if res:
            raise CommandError('Cannot delete lib/ directory.')

        self.stdout.write(self.style.WARNING("Running 'compilestatic'"))
        res = system('python manage.py compilestatic')
        if res:
            raise CommandError('compilestatic failed.')

        self.stdout.write(self.style.WARNING("Running 'collectstatic'"))
        res = system('python manage.py collectstatic --ignore=*.scss')
        if res:
            raise CommandError('collectstatic failed.')

        self.stdout.write(self.style.WARNING("Creating 'lib/' directory."))
        res = system('mkdir -p lib')
        if res:
            raise CommandError('Failed to create lib directory.')

        self.stdout.write(self.style.WARNING(
            "Installing requirements to 'lib/'"))
        res = system('pip install -t lib/ -r requirements.txt')
        if res:
            raise CommandError('Cannot install pip requirements.')

        self.stdout.write(self.style.WARNING("Deploying to gcloud."))
        res = system('gcloud app deploy')
        if res:
            raise CommandError('Failed to deploy app.')
        self.stdout.write(self.style.SUCCESS(
            'Successfully deployed app to gcloud.'))

        self.stdout.write(self.style.WARNING("Clearing 'static/' directory."))
        res = system('rm -rf static/')
        if res:
            raise CommandError('Cannot delete static/ directory.')

        self.stdout.write(self.style.WARNING("Running compilestatic."))
        res = system('python manage.py compilestatic')
        if res:
            raise CommandError('Failed to compilestatic.')

        self.stdout.write(self.style.WARNING("Clearing 'lib/' directory."))
        res = system('rm -rf lib/')
        if res:
            raise CommandError('Cannot delete lib/ directory.')
