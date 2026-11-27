import datetime

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError

from apps.financas.datas import parse_mes, somar_meses, vencimento_no_mes
from apps.financas.models import Ocorrencia
from apps.financas.services.ocorrencias import gerar_ocorrencias, sincronizar_recorrencia

from .factories import OcorrenciaFactory, RecorrenciaFactory, TransacaoFactory

pytestmark = pytest.mark.django_db
d = datetime.date


@pytest.mark.parametrize(
    ("mes", "dia", "esperado"),
    [
        (d(2026, 4, 1), 31, d(2026, 4, 30)),
        (d(2026, 2, 1), 31, d(2026, 2, 28)),
        (d(2026, 2, 1), 29, d(2026, 2, 28)),
        (d(2028, 2, 1), 31, d(2028, 2, 29)),  # bissexto
        (d(2026, 12, 1), 31, d(2026, 12, 31)),
        (d(2026, 6, 1), 5, d(2026, 6, 5)),
    ],
)
def test_vencimento_no_mes(mes, dia, esperado):
    assert vencimento_no_mes(mes, dia) == esperado


def test_somar_meses_e_parse():
    assert somar_meses(d(2026, 12, 1), 1) == d(2027, 1, 1)
    assert somar_meses(d(2026, 1, 1), -1) == d(2025, 12, 1)
    assert parse_mes("2026-02") == d(2026, 2, 1)
    with pytest.raises(ValueError):
        parse_mes("02/2026")


def test_gera_ocorrencia_com_ultimo_dia_em_fevereiro(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=31, valor_previsto_centavos=12_345)
    assert gerar_ocorrencias(usuario, d(2026, 2, 15)) == 1
    ocorrencia = Ocorrencia.objects.get()
    assert ocorrencia.recorrencia == rec
    assert ocorrencia.mes_referencia == d(2026, 2, 1)
    assert ocorrencia.vencimento == d(2026, 2, 28)
    assert ocorrencia.valor_centavos == 12_345
    assert ocorrencia.status == "prevista"


def test_gerar_e_idempotente(usuario):
    RecorrenciaFactory.create_batch(2, usuario=usuario)
    assert gerar_ocorrencias(usuario, d(2026, 3, 1)) == 2
    assert gerar_ocorrencias(usuario, d(2026, 3, 1)) == 0
    assert Ocorrencia.objects.count() == 2


def test_nao_gera_inativa_de_outro_usuario_antes_do_inicio_ou_depois_do_fim(usuario, outro_usuario):
    RecorrenciaFactory(usuario=usuario, ativa=False)
    RecorrenciaFactory(usuario=outro_usuario)
    RecorrenciaFactory(usuario=usuario, inicio=d(2026, 6, 1))
    RecorrenciaFactory(usuario=usuario, inicio=d(2026, 1, 1), fim=d(2026, 4, 30))
    assert gerar_ocorrencias(usuario, d(2026, 5, 1)) == 0


def test_inicio_depois_do_vencimento_comeca_no_mes_seguinte(usuario):
    rec = RecorrenciaFactory(usuario=usuario, inicio=d(2026, 11, 15), dia_do_mes=5)
    assert not rec.vale_para(d(2026, 11, 1))
    assert rec.vale_para(d(2026, 12, 1))


def test_fim_no_meio_do_mes(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=20, fim=d(2026, 12, 10))
    assert rec.vale_para(d(2026, 11, 1))
    assert not rec.vale_para(d(2026, 12, 1))


def test_parcelado_gera_so_o_total_de_parcelas(usuario):
    RecorrenciaFactory(usuario=usuario, inicio=d(2026, 1, 1), total_parcelas=3)
    meses = [d(2026, m, 1) for m in range(1, 7)]
    assert [gerar_ocorrencias(usuario, m) for m in meses] == [1, 1, 1, 0, 0, 0]


def test_unica_por_recorrencia_e_mes(usuario):
    oc = OcorrenciaFactory(recorrencia__usuario=usuario)
    with pytest.raises(IntegrityError):
        OcorrenciaFactory(recorrencia=oc.recorrencia, mes_referencia=oc.mes_referencia)


def test_status_atrasada_e_calculado(usuario):
    oc = OcorrenciaFactory(recorrencia__usuario=usuario, vencimento=d(2026, 11, 10))
    assert oc.status_em(d(2026, 11, 10)) == "prevista"
    assert oc.status_em(d(2026, 11, 11)) == "atrasada"
    oc.status = "paga"
    assert oc.status_em(d(2026, 11, 11)) == "paga"


# --- sincronizar_recorrencia ----------------------------------------------------

HOJE = d(2026, 11, 20)


def test_criar_recorrencia_gera_o_mes_atual(usuario):
    rec = RecorrenciaFactory(usuario=usuario)
    sincronizar_recorrencia(rec, hoje=HOJE)
    assert rec.ocorrencias.get().mes_referencia == d(2026, 11, 1)


def test_editar_atualiza_previstas_do_mes_atual_em_diante(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=100)
    passada = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 10, 1))
    atual = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 11, 1))
    futura = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 12, 1))
    paga = OcorrenciaFactory(
        recorrencia=rec, mes_referencia=d(2027, 1, 1), status="paga", paga_em=HOJE
    )
    rec.valor_previsto_centavos, rec.dia_do_mes = 999, 31
    rec.save()
    sincronizar_recorrencia(rec, hoje=HOJE)
    for o in (passada, atual, futura, paga):
        o.refresh_from_db()
    assert (passada.valor_centavos, passada.vencimento) == (100, d(2026, 10, 10))
    assert (atual.valor_centavos, atual.vencimento) == (999, d(2026, 11, 30))
    assert (futura.valor_centavos, futura.vencimento) == (999, d(2026, 12, 31))
    assert (paga.valor_centavos, paga.vencimento) == (100, d(2027, 1, 10))


def test_desativar_apaga_previstas_futuras_e_mantem_pagas_e_atrasadas(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=10)
    atrasada = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 11, 1))
    futura = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 12, 1))
    paga = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2027, 1, 1), status="paga")
    rec.ativa = False
    rec.save()
    sincronizar_recorrencia(rec, hoje=HOJE)
    restantes = set(rec.ocorrencias.values_list("pk", flat=True))
    assert restantes == {atrasada.pk, paga.pk}
    assert futura.pk not in restantes


def test_definir_fim_apaga_previstas_depois_do_fim(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=10)
    nov = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 11, 1))
    OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 12, 1))
    jan_paga = OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2027, 1, 1), status="paga")
    rec.fim = d(2026, 11, 30)
    rec.save()
    sincronizar_recorrencia(rec, hoje=HOJE)
    assert set(rec.ocorrencias.values_list("pk", flat=True)) == {nov.pk, jan_paga.pk}


def test_reduzir_parcelas_apaga_previstas_excedentes(usuario):
    rec = RecorrenciaFactory(usuario=usuario, inicio=d(2026, 10, 1), total_parcelas=4)
    for m in (d(2026, 11, 1), d(2026, 12, 1), d(2027, 1, 1)):
        OcorrenciaFactory(recorrencia=rec, mes_referencia=m)
    rec.total_parcelas = 2
    rec.save()
    sincronizar_recorrencia(rec, hoje=HOJE)
    assert list(rec.ocorrencias.values_list("mes_referencia", flat=True)) == [d(2026, 11, 1)]


def test_ocorrencia_paga_nao_e_apagada_ao_excluir_transacao(usuario):
    transacao = TransacaoFactory(usuario=usuario)
    oc = OcorrenciaFactory(recorrencia__usuario=usuario, status="paga", transacao=transacao)
    transacao.delete()
    oc.refresh_from_db()
    assert oc.transacao is None


# --- comando --------------------------------------------------------------------


def test_comando_gerar_ocorrencias(usuario, outro_usuario, capsys):
    RecorrenciaFactory(usuario=usuario)
    RecorrenciaFactory(usuario=outro_usuario)
    call_command("gerar_ocorrencias", "--mes", "2026-12")
    assert "2 ocorrência(s) criada(s) em 12/2026" in capsys.readouterr().out
    call_command("gerar_ocorrencias", "--mes", "2026-12", "--email", usuario.email)
    assert "0 ocorrência(s)" in capsys.readouterr().out


def test_comando_com_mes_invalido():
    with pytest.raises(CommandError):
        call_command("gerar_ocorrencias", "--mes", "12-2026")
