"""Rotas da API versão 1 (/api/v1/). Cada app registra suas rotas aqui."""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.urls")),
]
