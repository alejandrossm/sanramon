from django.contrib.admin.apps import AdminConfig


class SanRamonAdminConfig(AdminConfig):
    """Configura el admin de Django con reglas propias del proyecto."""

    default_site = 'config.admin.SuperuserOnlyAdminSite'
