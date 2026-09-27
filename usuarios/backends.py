from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailOrUsernameBackend(ModelBackend):
    """Permite iniciar sesion con username o correo electronico."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Busca el usuario por username/email y valida su password."""
        UserModel = get_user_model()
        login = username or kwargs.get(UserModel.USERNAME_FIELD)
        if login is None or password is None:
            return None

        internos = UserModel.objects.exclude(rol=UserModel.SOCIO)
        candidatos = list(internos.filter(username__iexact=login))
        candidatos.extend(
            internos.filter(email__iexact=login)
            .exclude(pk__in=[usuario.pk for usuario in candidatos])
        )
        if not candidatos:
            candidatos.extend(UserModel.objects.filter(username__iexact=login))
        if not candidatos:
            candidatos.extend(
                UserModel.objects.filter(
                    rol=UserModel.SOCIO,
                    email__iexact=login,
                )
            )

        for user in candidatos:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        if not candidatos:
            UserModel().set_password(password)
        return None
