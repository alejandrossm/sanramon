from django.contrib.admin import AdminSite


class SuperuserOnlyAdminSite(AdminSite):
    """Admin de Django restringido exclusivamente a superusuarios activos."""

    def has_permission(self, request):
        """Permite entrar al admin solo a superusuarios activos."""
        return request.user.is_active and request.user.is_superuser
