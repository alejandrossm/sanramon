from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Permite iniciar sesion con username o correo electronico."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Busca el usuario por username/email y valida su password."""
        UserModel = get_user_model()
        login = username or kwargs.get(UserModel.USERNAME_FIELD)
        if login is None or password is None:
            return None

        try:
            user = UserModel.objects.get(Q(username__iexact=login) | Q(email__iexact=login))
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
