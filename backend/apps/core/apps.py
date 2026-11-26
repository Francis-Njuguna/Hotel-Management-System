from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        from .access import sync_roles
        post_migrate.connect(sync_roles, sender=self, dispatch_uid='hotel_a_roles')
