from rest_framework.routers import SimpleRouter

from . import views

app_name = "financas"

router = SimpleRouter()
router.register("categorias", views.CategoriaViewSet, basename="categoria")
router.register("contas", views.ContaFinanceiraViewSet, basename="conta")
router.register("transacoes", views.TransacaoViewSet, basename="transacao")
router.register("regras", views.RegraCategoriaViewSet, basename="regra")
router.register("recorrencias", views.RecorrenciaViewSet, basename="recorrencia")
router.register("ocorrencias", views.OcorrenciaViewSet, basename="ocorrencia")
router.register("orcamentos", views.OrcamentoViewSet, basename="orcamento")

urlpatterns = router.urls
