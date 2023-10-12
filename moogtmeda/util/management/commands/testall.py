import sys
from os import system, WEXITSTATUS

from django.core.management.base import BaseCommand

# All APPs that should be tested, along with the correct setting to use
# for their tests.
APPS_AND_SETTINGS = {'api': 'moogtmeda.settings.testing',
                     'arguments': 'moogtmeda.settings.testing',
                     'chat': 'moogtmeda.settings.testing',
                     'invitations': 'moogtmeda.settings.testing',
                     'moogts': 'moogtmeda.settings.testing',
                     'polls': 'moogtmeda.settings.testing',
                     'views': 'moogtmeda.settings.testing',
                     'notifications': 'notifications.tests.settings',
                     'meda': 'moogtmeda.settings.testing',
                     'users': 'moogtmeda.settings.testing',
                     }


class Command(BaseCommand):
    help = 'Runs all the tests in Moogter with appropriate settings. '

    def handle(self, *args, **options):
        for app in APPS_AND_SETTINGS:
            self.stdout.write(self.style.WARNING("Testing app '" + app + "'."))
            cmd = system('python manage.py test ' + app + ' --settings ' +
                         APPS_AND_SETTINGS[app])
            if WEXITSTATUS(cmd) != 0:
                # Test failed
                sys.exit(1)
