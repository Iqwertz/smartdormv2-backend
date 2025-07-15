from django.apps import AppConfig
from django.db.models.signals import post_migrate
import logging

logger = logging.getLogger(__name__)

def initialize_global_settings(sender, **kwargs):
    """
    Signal handler to initialize GlobalAppSettings after migrations for this app.
    This function will be called once migrations for the 'smartdorm' app have run.
    """
    # Import the model locally to avoid AppRegistryNotReady errors during Django startup
    from .models import GlobalAppSettings
    
    try:
        # This will create the instance with default values if it doesn't exist.
        # It relies on migrations having successfully created the 't_global_app_settings' table.
        GlobalAppSettings.load()
        logger.info("GlobalAppSettings initialization check complete. Settings loaded or created.")
    except Exception as e:
        # This exception typically occurs if the 't_global_app_settings' table does not exist
        # (e.g., migrations failed or were not run for this model).
        # It's crucial to run migrations to create the table schema.
        logger.error(
            f"Failed to initialize GlobalAppSettings: {e}. "
            f"This likely means the '{GlobalAppSettings._meta.db_table}' table is missing. "
            "Please ensure migrations have been run successfully: "
            "'python manage.py makemigrations smartdorm' and 'python manage.py migrate smartdorm'."
        )

class SmartdormConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'smartdorm'

    def ready(self):
        """
        Called when the application is ready.
        We connect the post_migrate signal here.
        """
        post_migrate.connect(initialize_global_settings, sender=self)
        logger.info("SmartdormConfig ready, post_migrate signal for GlobalAppSettings connected.")