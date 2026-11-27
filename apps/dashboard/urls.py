from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("dashboard/resumo/", views.ResumoView.as_view(), name="resumo"),
    path("dashboard/evolucao/", views.EvolucaoView.as_view(), name="evolucao"),
]
