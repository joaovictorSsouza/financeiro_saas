from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    RegistroSerializer,
    TokensSerializer,
    UsuarioSerializer,
)


class ViewPublica(APIView):
    """Sem autenticação (um Bearer vencido no header não deve bloquear login/registro),
    mas ainda devolvendo 401 com WWW-Authenticate em falha de credenciais."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


class RegistroView(ViewPublica):
    """Cria uma conta a partir de um código de convite válido e já devolve os tokens."""

    throttle_scope = "registro"

    @extend_schema(
        request=RegistroSerializer,
        responses={
            201: inline_serializer(
                "RegistroResposta",
                {
                    "usuario": UsuarioSerializer(),
                    "access": serializers.CharField(),
                    "refresh": serializers.CharField(),
                },
            )
        },
        tags=["auth"],
    )
    def post(self, request):
        serializer = RegistroSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        dados = {"usuario": UsuarioSerializer(usuario).data, **services.gerar_tokens(usuario)}
        return Response(dados, status=status.HTTP_201_CREATED)


class LoginView(ViewPublica):
    """Autentica por e-mail e senha e devolve access e refresh."""

    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: TokensSerializer}, tags=["auth"])
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(services.gerar_tokens(serializer.validated_data["usuario"]))


class LogoutView(APIView):
    """Invalida (blacklist) o refresh token informado."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer, responses={204: None}, tags=["auth"])
    def post(self, request):
        serializer = LogoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.validated_data["refresh"].blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH dos dados do usuário autenticado. O objeto é sempre `request.user`."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    @extend_schema(tags=["conta"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["conta"])
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        return self.request.user
