import pytest

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/"


def test_me_exige_autenticacao(api_client):
    assert api_client.get(URL).status_code == 401


def test_me_retorna_o_proprio_usuario(cliente_autenticado, usuario):
    resposta = cliente_autenticado.get(URL)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == str(usuario.id)
    assert corpo["email"] == usuario.email
    assert "password" not in corpo


def test_patch_atualiza_nome(cliente_autenticado, usuario):
    resposta = cliente_autenticado.patch(URL, {"nome": "Novo Nome"})
    assert resposta.status_code == 200
    usuario.refresh_from_db()
    assert usuario.nome == "Novo Nome"


def test_patch_ignora_campos_somente_leitura(cliente_autenticado, usuario):
    email_original = usuario.email
    cliente_autenticado.patch(
        URL, {"email": "hack@exemplo.com", "is_staff": True, "is_superuser": True}
    )
    usuario.refresh_from_db()
    assert usuario.email == email_original
    assert not usuario.is_staff
    assert not usuario.is_superuser


def test_put_nao_permitido(cliente_autenticado):
    assert cliente_autenticado.put(URL, {"nome": "x"}).status_code == 405


def test_usuario_nao_acessa_nem_altera_dados_de_outro(cliente_autenticado, usuario, outro_usuario):
    """Regra permanente 4: um usuário nunca vê nem altera dados de outro."""
    nome_do_outro = outro_usuario.nome

    resposta = cliente_autenticado.get(URL, {"id": str(outro_usuario.id)})
    assert resposta.json()["id"] == str(usuario.id)
    assert outro_usuario.email not in resposta.content.decode()

    cliente_autenticado.patch(URL, {"id": str(outro_usuario.id), "nome": "Invadido"})
    outro_usuario.refresh_from_db()
    assert outro_usuario.nome == nome_do_outro
    usuario.refresh_from_db()
    assert usuario.nome == "Invadido"
