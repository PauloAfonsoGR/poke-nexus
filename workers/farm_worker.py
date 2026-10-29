"""A rotina de farm de UMA conta.

O farm em si é feito pelo servidor do PokeIdle: estando numa hunt, as batalhas
acontecem sozinhas. Esta rotina só age quando precisa:
  - a conta não está numa hunt          -> entra na hunt
  - o time caiu e foi para o Centro     -> cura e volta para a hunt
  - o servidor parou de responder       -> recarrega a página
  - nova versão do jogo                 -> recarrega pelo botão do próprio jogo
Telas que pedem uma pessoa (login, termos, conta aberta em outro lugar...) só
mudam o status; o programa nunca clica nelas.
"""
import asyncio
import time

from game import selectors as S
from game.pokeidle import ERROS_DE_SESSAO, diagnostico_recusa

OFFLINE = "OFFLINE"
INICIANDO = "INICIANDO"
FARMING = "FARMING"
BATALHA = "BATALHA"
AGUARDANDO = "AGUARDANDO"
PAUSADO = "PAUSADO"
MANUAL = "MANUAL"
ERRO = "ERRO"
SESSAO_EXPIRADA = "SESSÃO EXPIRADA"


class FarmRoutine:
    def __init__(self, worker):
        self.w = worker
        self.cfg_int = worker.cfg["intervalos"]
        self.cfg_farm = worker.cfg["farm"]
        self.defeats: list[float] = []
        self.center_since: float | None = None
        self.next_hunt_try = 0.0
        self.reload_backoff = 0.0
        self.next_reload = 0.0

    # ------------------------------------------------------------ helpers
    @property
    def g(self):
        return self.w.game

    def register_defeat(self):
        now = time.monotonic()
        janela = self.cfg_farm["janela_derrotas_minutos"] * 60
        self.defeats = [t for t in self.defeats if now - t < janela] + [now]

    def too_many_defeats(self) -> bool:
        now = time.monotonic()
        janela = self.cfg_farm["janela_derrotas_minutos"] * 60
        return len([t for t in self.defeats if now - t < janela]) >= self.cfg_farm["max_derrotas"]

    def target_hunt(self) -> str | None:
        return self.w.acc.hunt or self.w.last_hunt or self.g.hunt_slug

    async def reload(self, motivo: str):
        now = time.monotonic()
        if now < self.next_reload:
            return
        self.w.log(f"{motivo} - recarregando a página")
        self.w.set_status(AGUARDANDO, "recarregando a página")
        try:
            await self.w.page.reload(timeout=60)
            self.reload_backoff = 0
        except Exception as e:
            self.reload_backoff = min(max(self.reload_backoff * 2, 15), 120)
            self.w.set_status(ERRO, "sem internet ou PokeIdle fora do ar")
            self.w.log(f"falha ao recarregar ({_curto(e)}) - nova tentativa em {self.reload_backoff:.0f}s")
        self.next_reload = time.monotonic() + max(self.reload_backoff, 20)
        self.g.last_msg_at = time.monotonic()
        self.g.last_battle_event_at = time.monotonic()

    async def go_hunt(self, slug: str):
        now = time.monotonic()
        if now < self.next_hunt_try:
            return
        nome = self.g.hunt_name(slug)
        self.w.set_status(AGUARDANDO, f"entrando em {nome}")
        self.w.log(f"entrando na hunt {nome}")
        self.w.last_action = f"entrar na hunt {nome}"
        try:
            ok = await self.g.enter_hunt(slug, self.w.cfg["url"])
        except Exception as e:
            ok = False
            self.w.log(f"erro ao entrar na hunt: {_curto(e)}")
        if ok:
            self.w.remember_hunt(slug)
            self.w.log(f"farm iniciado em {nome}")
            self.g.last_battle_event_at = time.monotonic()
            self.center_since = None
        else:
            self.w.log(f"não consegui entrar em {nome} - nova tentativa em 30s")
            self.next_hunt_try = time.monotonic() + 30

    # ------------------------------------------------------------- passo
    async def step(self):
        w, g = self.w, self.g

        if w.mode == "manual":
            w.set_status(MANUAL, "você está no controle")
            return
        if w.mode == "pausado":
            w.set_status(PAUSADO, "automação pausada")
            return

        tela = await g.read_screen()

        if w.recheck:
            # Voltando do manual/pausa: não confia no que via antes.
            w.recheck = False
            w.log("verificando o estado atual do jogo")
            self.center_since = None
            self.next_hunt_try = 0
            self.defeats.clear()
            await g.wait_change(3)
            tela = await g.read_screen()

        # ---- telas que exigem uma pessoa
        if g.error_key and g.error_key not in ERROS_DE_SESSAO:
            w.set_status(ERRO, f"servidor recusou: {diagnostico_recusa(g.error_key)}")
            return
        if tela[S.TELA_LOGIN] or g.error_key in ERROS_DE_SESSAO:
            w.set_status(SESSAO_EXPIRADA, "faça login: botão 'Login' do programa")
            return
        if tela[S.SESSAO_TOMADA]:
            w.set_status(ERRO, "conta aberta em outro lugar - assuma o controle e clique 'Jogar aqui'")
            return
        if tela[S.ALERTA_CONTA]:
            w.set_status(ERRO, tela.get("alerta_texto") or "aviso da conta no jogo")
            return
        for tela_id, pedido in S.TELAS_MANUAIS.items():
            if tela.get(tela_id):
                w.set_status(AGUARDANDO, f"ação manual: {pedido}")
                return
        if tela[S.AVISO_VERSAO]:
            w.log("nova versão do jogo - recarregando pelo botão do jogo")
            w.last_action = "recarregar nova versão"
            try:
                await g.click_reload_version()
            except Exception:
                await self.reload("nova versão do jogo")
            return

        # ---- conexão
        quieto = time.monotonic() - g.last_msg_at
        if quieto > self.cfg_int["sem_resposta_recarregar_segundos"]:
            await self.reload(f"sem resposta do servidor há {quieto:.0f}s")
            return
        if not g.welcomed:
            w.set_status(AGUARDANDO, "conectando ao servidor..." if not tela[S.TELA_CARREGANDO]
                         else "carregando o jogo...")
            return

        # ---- onde o jogador está
        cena = g.em_outra_cena
        if cena:
            w.set_status(AGUARDANDO, f"em {cena} - o programa não mexe")
            return

        if g.hunt_slug and not g.no_centro:
            w.remember_hunt(g.hunt_slug)
            self.center_since = None
            sem_batalha = time.monotonic() - g.last_battle_event_at
            if sem_batalha > self.cfg_int["sem_batalha_recarregar_segundos"]:
                await self.reload(f"nenhuma batalha há {sem_batalha:.0f}s")
                return
            w.set_status(BATALHA if g.in_battle else FARMING, g.hunt_name(g.hunt_slug))
            return

        alvo = self.target_hunt()
        if g.no_centro:
            now = time.monotonic()
            if self.center_since is None:
                self.center_since = now
            if not self.cfg_farm["voltar_apos_derrota"]:
                w.set_status(AGUARDANDO, "no Centro Pokémon (volta automática desligada no config)")
                return
            if self.too_many_defeats():
                w.mode = "pausado"
                w.set_status(PAUSADO, "muitas derrotas seguidas")
                w.log(f"o time caiu {len(self.defeats)}x em pouco tempo - automação PAUSADA "
                      "para não perder XP (troque de área ou fortaleça o time e retome)")
                return
            espera = self.cfg_int["espera_volta_automatica_segundos"]
            if g.auto_voltar_hunt and now - self.center_since < espera:
                w.set_status(AGUARDANDO, "no Centro - aguardando a volta automática do jogo")
                return
            if not alvo:
                w.set_status(AGUARDANDO, "no Centro - escolha uma área no Mapa (modo manual)")
                return
            if await g.heal():
                w.log("equipe curada no Centro Pokémon")
                w.last_action = "curar equipe"
                await asyncio.sleep(2)
            await self.go_hunt(alvo)
            return

        if not alvo:
            w.set_status(AGUARDANDO, "escolha uma área no Mapa uma vez (Assumir controle)")
            return
        await self.go_hunt(alvo)


def _curto(e: Exception) -> str:
    return (str(e).strip().splitlines() or [type(e).__name__])[0][:120]
