"""Verificação padrão de isolamento: recurso de outro usuário é sempre 404."""


def verificar_isolamento(cliente, url_base, objeto_alheio, dados_edicao):
    url = f"{url_base}{objeto_alheio.pk}/"
    ids = [item["id"] for item in cliente.get(url_base).json()["results"]]
    assert str(objeto_alheio.pk) not in ids
    assert cliente.get(url).status_code == 404
    assert cliente.patch(url, dados_edicao).status_code == 404
    assert cliente.put(url, dados_edicao).status_code == 404
    assert cliente.delete(url).status_code == 404
    assert type(objeto_alheio).objects.filter(pk=objeto_alheio.pk).exists()
