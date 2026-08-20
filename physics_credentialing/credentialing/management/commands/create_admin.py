from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from credentialing.models import UserProfile


class Command(BaseCommand):
    help = 'Create the initial admin login (interactive-free, for first setup)'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', required=True)

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=options['username'],
            defaults={'is_staff': True, 'is_superuser': True})
        user.set_password(options['password'])
        user.is_staff = True
        user.is_superuser = True
        user.save()
        UserProfile.objects.update_or_create(user=user, defaults={'role': 'admin'})
        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f"{verb} admin user '{user.username}'."))
