from os import system
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = 'Builds the angular web client.'

    def handle(self, *args, **options):
        self.stdout.write('Building web client...')
        command = 'cd ../moogter-web && ' \
                  'ng build --prod --output-path ../moogtmeda/meda/static/web --output-hashing none'
        system(command)



