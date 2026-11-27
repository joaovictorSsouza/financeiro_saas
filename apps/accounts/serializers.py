from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from . import services
from .managers import normalizar_email
from .models import Usuario


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("id", "email", "nome", "criado_em")
        read_only_fields = fields


class TokensSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class RegistroSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=64, write_only=True)
    email = serializers.EmailField(write_only=True)
    senha = serializers.CharField(write_only=True, style={"input_type": "password"})
    nome = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        candidato = Usuario(email=normalizar_email(attrs["email"]), nome=attrs.get("nome", ""))
        try:
            password_validation.validate_password(attrs["senha"], user=candidato)
        except DjangoValidationError as erro:
            raise serializers.ValidationError({"senha": list(erro.messages)}) from erro
        return attrs

    def create(self, validated_data):
        try:
            return services.registrar_com_convite(**validated_data)
        except services.ConviteInvalido as erro:
            raise serializers.ValidationError(
                {"codigo": ["Convite inválido, expirado ou já utilizado."]}
            ) from erro
        except services.EmailJaCadastrado as erro:
            raise serializers.ValidationError(
                {"email": ["Já existe uma conta com este e-mail."]}
            ) from erro


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    senha = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        usuario = authenticate(
            request=self.context.get("request"),
            email=normalizar_email(attrs["email"]),
            password=attrs["senha"],
        )
        if usuario is None or not usuario.is_active:
            raise AuthenticationFailed("E-mail ou senha inválidos.")
        attrs["usuario"] = usuario
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, valor):
        try:
            token = RefreshToken(valor)
        except TokenError as erro:
            raise serializers.ValidationError("Token inválido ou expirado.") from erro
        usuario = self.context["request"].user
        if str(token.get("user_id")) != str(usuario.pk):
            raise serializers.ValidationError("Token inválido ou expirado.")
        return token
