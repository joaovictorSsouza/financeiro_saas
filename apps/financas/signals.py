from django.dispatch import receiver

from apps.accounts.signals import usuario_registrado

from .services.categorias import criar_categorias_padrao


@receiver(usuario_registrado, dispatch_uid="financas_categorias_padrao")
def _criar_categorias_do_novo_usuario(sender, usuario, **kwargs):
    criar_categorias_padrao(usuario)
