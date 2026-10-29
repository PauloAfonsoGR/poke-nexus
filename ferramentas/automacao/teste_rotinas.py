"""Regressões sem contas reais: configuração, vagas, partidas e retomada de hunt.

python -m unittest discover -s ferramentas/automacao -p teste_rotinas.py -v
"""
import asyncio
import os
import tempfile
import time
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

_dados = tempfile.TemporaryDirectory(prefix="pokenexus_testes_", dir=os.environ.get("POKENEXUS_TEST_TMP"))
os.environ["POKENEXUS_DATA"] = _dados.name

from app.config import Account, DEFAULTS, load_config
from app.config_edit import ErroConfig, salvar, validar
from app.manager import Manager
from game import selectors as S
from hunts.analyzer import recomendar_hunt_automatica
from workers.account_worker import AccountWorker
from workers.farm_worker import FarmRoutine, ERRO, FARMING, SESSAO_EXPIRADA


class Configuracao(unittest.TestCase):
    def config(self, texto):
        p = Path(_dados.name) / "teste.toml"
        p.write_text(texto, encoding="utf-8")
        return load_config(p)

    def test_limite_atual_preservado(self):
        cfg, contas = self.config("quantidade_contas = 8\nmax_simultaneas = 8\n")
        self.assertEqual((len(contas), cfg["max_simultaneas"]), (4, 4))
        self.assertEqual(len({a.folder for a in contas}), 4)
        self.assertEqual(contas[-1].folder, "conta_04")
        self.assertTrue(cfg["iniciar_contas_ao_abrir"])

    def test_configuracao_antiga_preservada(self):
        cfg, contas = self.config('iniciar_contas_ao_abrir = false\n[[contas]]\npasta="principal"\nhunt="bosque"\n')
        self.assertFalse(cfg["iniciar_contas_ao_abrir"])
        self.assertEqual((contas[0].folder, contas[0].hunt), ("principal", "bosque"))

    def test_valores_invalidos_recusados(self):
        for campo in ("quantidade_contas", "max_simultaneas"):
            for valor in ("0", "-1", "true", "1.5", '"8"'):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                    self.config(f"{campo} = {valor}")

    def test_perfis_nao_colidem_no_windows(self):
        with self.assertRaises(ValueError):
            self.config('quantidade_contas=2\n[[contas]]\npasta="Conta"\n[[contas]]\npasta="conta"')

    def test_perfis_nao_escapam_da_pasta(self):
        with self.assertRaises(ValueError):
            self.config('[[contas]]\npasta="../fora"')

    def test_defaults_nao_sao_compartilhados(self):
        cfg, _ = self.config("")
        cfg["farm"]["max_derrotas"] = 49
        self.assertEqual(DEFAULTS["farm"]["max_derrotas"], 3)

    def test_salvar_com_comentarios_e_ler_de_volta(self):
        p = Path(_dados.name) / "salvar.toml"
        p.write_text("# preservado\nquantidade_contas = 4 # quantidade\n", encoding="utf-8")
        salvar(p, {(None, "quantidade_contas"): 3, (None, "max_simultaneas"): 3}, [])
        self.assertIn("# quantidade", p.read_text(encoding="utf-8"))
        self.assertEqual(len(load_config(p)[1]), 3)
        with self.assertRaises(ErroConfig):
            validar({(None, "max_simultaneas"): 0}, [])

    def test_opcoes_do_otimizador_sao_validadas(self):
        validar({("farm", "objetivo_hunt"): "ouro", ("farm", "risco_maximo_hunt"): "baixo",
                 ("farm", "usar_medicoes_reais"): True}, [])
        with self.assertRaises(ErroConfig):
            validar({("farm", "objetivo_hunt"): "qualquer"}, [])
        with self.assertRaises(ErroConfig):
            validar({("farm", "risco_maximo_hunt"): "alto"}, [])


class MelhorHunt(unittest.TestCase):
    @staticmethod
    def linha(slug, xp, risco=0.2, liberada=True, inviavel=False, nivel=1, mortes=0, um_hit=False):
        return {"slug": slug, "xp_pokemon_h": xp, "hit_pct": risco, "liberada": liberada,
                "xp_treinador_h": xp * 2, "ouro_h": xp / 2, "kph": 100, "kph_modelo": 100,
                "inviavel": inviavel, "nivel": nivel, "mortes_h": mortes, "um_hit": um_hit}

    def test_escolhe_maior_xp_segura_e_liberada(self):
        r = {"todas": [self.linha("atual", 100), self.linha("segura", 140),
                       self.linha("perigosa", 500, um_hit=True),
                       self.linha("travada", 800, liberada=False)]}
        self.assertEqual(recomendar_hunt_automatica(r, "atual", 10)["slug"], "segura")

    def test_nao_troca_por_variacao_pequena(self):
        r = {"todas": [self.linha("atual", 100), self.linha("outra", 109)]}
        self.assertIsNone(recomendar_hunt_automatica(r, "atual", 10))

    def test_sai_de_hunt_de_risco_alto(self):
        r = {"todas": [self.linha("atual", 300, um_hit=True), self.linha("segura", 100)]}
        self.assertEqual(recomendar_hunt_automatica(r, "atual", 50)["slug"], "segura")

    def test_objetivo_ouro_pode_escolher_outra_hunt(self):
        atual, ouro = self.linha("atual", 150), self.linha("ouro", 100)
        ouro["ouro_h"] = 300
        r = {"todas": [atual, ouro]}
        self.assertEqual(recomendar_hunt_automatica(r, "atual", 5, "ouro")["slug"], "ouro")

    def test_medicao_real_corrige_ranking(self):
        atual, teorica = self.linha("atual", 100), self.linha("teorica", 120)
        atual["kph_medido"], teorica["kph_medido"] = 140, 60
        r = {"todas": [atual, teorica]}
        self.assertIsNone(recomendar_hunt_automatica(r, "atual", 5, usar_medicoes_reais=True))
        self.assertEqual(recomendar_hunt_automatica(r, "atual", 5, usar_medicoes_reais=False)["slug"], "teorica")

    def test_risco_baixo_exclui_hunt_media(self):
        r = {"todas": [self.linha("atual", 100), self.linha("media", 200, risco=0.6)]}
        self.assertIsNone(recomendar_hunt_automatica(r, "atual", 5, risco_maximo="baixo"))


class ContaFalsa:
    def __init__(self, i):
        self.acc = SimpleNamespace(index=i, name=f"Conta {i}", enabled=True)
        self.running = self.pending_start = self.login_open = False
        self.inicios = []

    def start(self, atraso=0):
        self.inicios.append(atraso)
        self.running, self.login_open = True, False

    async def open_login(self, _url):
        await asyncio.sleep(.01)
        self.login_open = True

    async def stop(self):
        self.running = self.login_open = False

    async def restart(self):
        await self.stop()
        self.start()


class Vagas(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.m = m = Manager.__new__(Manager)
        m.cfg = {"max_simultaneas": 4, "intervalo_inicio_segundos": 3, "url": "about:blank"}
        m.workers = [ContaFalsa(i) for i in range(5)]
        m._reservas, m._reserva_lock, m._comandos = Counter(), RLock(), {}
        m._log = Mock()
        self.tarefas = []
        def agendar(fn, *args):
            t = asyncio.create_task(fn(*args))
            self.tarefas.append(t)
            return t
        m._call = agendar

    async def drenar(self):
        await asyncio.gather(*self.tarefas)

    async def test_quatro_partidas_espacadas_e_quinta_recusada(self):
        self.m.start_all()
        self.assertEqual(self.m.connected_count(), 4)
        self.assertFalse(self.m.start_account(4)[0])
        await self.drenar()
        self.assertEqual([w.inicios for w in self.m.workers[:4]], [[i * 3] for i in range(4)])

    async def test_login_reserva_vaga_antes_de_abrir(self):
        self.m.cfg["max_simultaneas"] = 1
        self.assertTrue(self.m.open_login(0)[0])
        self.assertFalse(self.m.open_login(1)[0])
        self.assertFalse(self.m.start_account(1)[0])
        await self.drenar()
        self.assertEqual(self.m.connected_count(), 1)

    async def test_parar_tudo_fecha_login_e_partida_pendente(self):
        self.m.open_login(0)
        self.m.start_account(1)
        self.m.stop_all()
        await self.drenar()
        self.assertEqual(self.m.connected_count(), 0)

    async def test_inicio_duplicado_e_idempotente(self):
        self.m.start_account(0)
        self.m.start_account(0)
        await self.drenar()
        self.assertEqual(self.m.workers[0].inicios, [0])

    async def test_falha_de_login_libera_reserva(self):
        self.m.workers[0].open_login = AsyncMock(side_effect=RuntimeError("teste"))
        self.m.open_login(0)
        with self.assertRaises(RuntimeError):
            await self.drenar()
        self.assertEqual(self.m.connected_count(), 0)

    async def test_reiniciar_parada_respeita_limite(self):
        self.m.cfg["max_simultaneas"] = 1
        self.m.start_account(0)
        self.assertFalse(self.m.restart_account(1)[0])
        await self.drenar()


class Farm(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.browser = SimpleNamespace(close_page=AsyncMock(), open_page=AsyncMock())
        self.w = w = AccountWorker(Account(0, "Teste", "teste", 25, "bosque", True),
                                   deepcopy(DEFAULTS), self.browser, Mock())
        tela = {k: False for k in (S.TELA_LOGIN, S.SESSAO_TOMADA, S.ALERTA_CONTA, S.AVISO_VERSAO,
                                  S.TELA_CARREGANDO, *S.TELAS_MANUAIS)}
        w.game = SimpleNamespace(read_screen=AsyncMock(return_value=tela), error_key=None,
                                 welcomed=True, last_msg_at=time.monotonic(), em_outra_cena=None,
                                 hunt_slug=None, no_centro=False, auto_voltar_hunt=False,
                                 hunt_name=lambda s: s, enter_hunt=AsyncMock(return_value=True),
                                 heal=AsyncMock(return_value=False), in_battle=False,
                                 last_battle_event_at=time.monotonic())
        self.f = FarmRoutine(w)

    async def test_sessao_valida_inicia_hunt_automaticamente(self):
        await self.f.step()
        self.w.game.enter_hunt.assert_awaited_once_with("bosque", self.w.cfg["url"])

    async def test_retomada_usa_ultima_hunt(self):
        self.w.acc.hunt, self.w.last_hunt = "", "ultima"
        await self.f.step()
        self.w.game.enter_hunt.assert_awaited_once_with("ultima", self.w.cfg["url"])

    async def test_centro_sem_historico_usa_hunt_do_servidor(self):
        self.w.acc.hunt, self.w.last_hunt = "", None
        self.w.game.hunt_slug, self.w.game.no_centro = "servidor", True
        await self.f.step()
        self.w.game.enter_hunt.assert_awaited_once_with("servidor", self.w.cfg["url"])

    async def test_login_exige_pessoa_sem_tentar_cacar(self):
        self.w.game.read_screen.return_value[S.TELA_LOGIN] = True
        await self.f.step()
        self.assertEqual(self.w.status, SESSAO_EXPIRADA)
        self.w.game.enter_hunt.assert_not_awaited()

    async def test_recusa_ip_explica_limite_sem_recarregar(self):
        self.w.game.error_key = "login.limiteOnlineIpLista"
        await self.f.step()
        self.assertEqual(self.w.status, ERRO)
        self.assertIn("IP/rede", self.w.detail)
        self.w.game.enter_hunt.assert_not_awaited()

    async def test_hunt_em_andamento_nao_reinicia(self):
        self.w.game.hunt_slug = "bosque"
        await self.f.step()
        self.assertEqual(self.w.status, FARMING)
        self.w.game.enter_hunt.assert_not_awaited()

    async def test_pausa_nao_le_dom(self):
        self.w.mode = "pausado"
        await self.f.step()
        self.w.game.read_screen.assert_not_awaited()

    async def test_partida_espacada_pode_ser_cancelada(self):
        self.w.start(atraso=60)
        await self.w.stop()
        self.assertFalse(self.w.running)
        self.browser.open_page.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
