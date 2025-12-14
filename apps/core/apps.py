from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    # CRITICAL FIX: Change name to the full path
    name = 'apps.core'