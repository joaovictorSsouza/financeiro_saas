import factory

from apps.accounts.models import Convite, Usuario

SENHA_PADRAO = "senha-forte-de-teste-123"


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"usuario{n}@exemplo.com")
    nome = factory.Faker("name", locale="pt_BR")
    password = factory.PostGenerationMethodCall("set_password", SENHA_PADRAO)

    @factory.post_generation
    def _salvar(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class ConviteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Convite

    criado_por = factory.SubFactory(UsuarioFactory)
