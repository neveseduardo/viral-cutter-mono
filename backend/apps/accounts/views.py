from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import TokenSerializer

User = get_user_model()


def _guest_user():
    user, _ = User.objects.get_or_create(
        username="guest",
        defaults={"is_active": True, "email": "guest@local"},
    )
    return user


class GuestLoginView(TokenObtainPairView):
    """Returns tokens for the implicit single user when AUTH_DISABLED=true."""

    serializer_class = TokenSerializer

    def post(self, request, *args, **kwargs):
        if settings.AUTH_DISABLED:
            user = _guest_user()
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {"username": user.username, "is_guest": True},
            })

        data = request.data
        username = data.get("username", "")
        password = data.get("password", "")
        user = User.objects.filter(username=username).first()
        if user is not None and user.check_password(password):
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {"username": user.username, "is_guest": False},
            })
        return Response(
            {"error": True, "code": "unauthorized", "detail": "Credenciais inválidas."},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class GuestRefreshView(APIView):
    def post(self, request, *args, **kwargs):
        if settings.AUTH_DISABLED:
            user = _guest_user()
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            })
        return Response({"error": True, "detail": "Not supported"}, status=400)