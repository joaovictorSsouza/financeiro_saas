"""Sinais do app de contas.

`usuario_registrado` é enviado quando um usuário se cadastra pelo convite. Outros apps
(ex.: `financas`, que cria as categorias padrão) escutam o sinal, assim `accounts` não
depende deles.
"""

from django.dispatch import Signal

# Argumentos: usuario
usuario_registrado = Signal()
