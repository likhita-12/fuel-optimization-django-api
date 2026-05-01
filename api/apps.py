from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Application config for API module."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
