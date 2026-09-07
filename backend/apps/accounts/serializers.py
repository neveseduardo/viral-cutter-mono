from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class GuestTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Allows login with any credentials in local single-user mode."""

    default_error_messages = {"no_active_account": "Credenciais inválidas."}

    def validate(self, attrs):
        if hasattr(self, "request") and getattr(self.request, "user", None):
            if getattr(self.request.user, "is_authenticated", False):
                attrs["username"] = self.request.user.get_username()
                attrs["password"] = "unused"
        return super().validate(attrs)


class TokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["is_guest"] = True
        return token