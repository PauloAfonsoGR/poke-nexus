"""Worker de UMA conta: abre a sessão (página embutida) dela, roda a rotina de farm
e se recupera de erros sem afetar as outras contas."""
import asyncio
import json
import time
from dataclasses import dataclass

from app.config import Account
from browser.browser_manager import BrowserManager
from browser.cdp import CdpPage
from game.pokeidle import GameSession
from hunts.analyzer import HuntAnalyzer, recomendar_hunt_automatica
from rmt.rotina import RmtRotina
from workers.farm_worker import (AGUARDANDO, ERRO, INICIANDO, OFFLINE, FarmRoutine, _curto)


class BrowserClosed(Exception):
    pass


@dataclass
class Stats:
    started_at: float | None = None     # time.monotonic() do início
    xp_gained: int = 0                  # soma do XP de treinador das batalhas - XP perdido
    battles: int = 0
    level: int | None = None
    nick: str | None = None
    last_battle: str = "-"
    defeats: int = 0
    ativo_especie: int | None = None    # speciesId do pokémon em campo (o que está sendo upado)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.started_at else 0.0

    @property
    def xp_per_hour(self) -> int | None:
        # Só mostra ritmo depois de 1 minuto (antes disso o número não significa nada).
        if not self.started_at or self.elapsed < 60 or self.battles == 0:
            return None
        return round(self.xp_gained / (self.elapsed / 3600))


class AccountWorker:
    def __init__(self, account: Account, cfg: dict, browser: BrowserManager, log, hunt_data=None,
                 proprios=lambda: set()):
        self.acc = account
        self.cfg = cfg
        self.browser = browser
        self._log = log
        self.status = OFFLINE
        self.detail = "parada"
        self.mode = "auto"              # auto | pausado | manual
        self.recheck = False
        self.last_action = "-"
        self.stats = Stats()
        self.task: asyncio.Task | None = None
        self.pending_start = False      # "Iniciar" clicado, tarefa ainda não criada
        self.page: CdpPage | None = None
        self.game: GameSession | None = None
        self.farm: FarmRoutine | None = None
        self.heartbeat = time.monotonic()
        self.login_open = False         # página de login SEM automação aberta (login reserva)
        self._state_file = account.profile_dir / "manager_state.json"
        estado = self._load_state()
        self.last_hunt = estado.get("last_hunt")
        # Quem é esta conta no jogo (nick e id), guardado para reconhecer os anúncios dela no RMT
        # mesmo quando ela está parada.
        self.identidade = {k: estado.get(k) for k in ("nick", "id")}
        # Hunt Analyzer e medição real DESTA conta (nada é compartilhado com as outras).
        self.hunts = HuntAnalyzer(account.profile_dir, hunt_data)
        self._melhor_hunt_em = time.monotonic() + 60
        # RMT (Mercado da Comunidade) DESTA conta: regras, limites e extrato no perfil dela.
        self.rmt = RmtRotina(self, hunt_data, proprios)

    # --------------------------------------------------------------- estado
    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def log(self, msg: str):
        self._log(self.acc.index, msg)

    def set_status(self, status: str, detail: str = ""):
        # Registra no log as mudanças importantes (pausa/manual já são registradas pelo comando).
        if status != self.status and (status in (ERRO, "SESSÃO EXPIRADA")
                                      or self.status in (ERRO, "SESSÃO EXPIRADA")):
            self.log(f"{status.lower()}" + (f" - {detail}" if detail else ""))
        self.status, self.detail = status, detail

    def remember_hunt(self, slug: str):
        if slug and slug != self.last_hunt:
            self.last_hunt = slug
            self._save_state(last_hunt=slug)

    def _save_state(self, **mudancas):
        try:
            estado = {**self._load_state(), **mudancas}
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(estado), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    # ------------------------------------------------------------- comandos
    def start(self, atraso: float = 0):
        self.pending_start = False
        if self.running:
            return
        self.login_open = False         # a sessão monitorada substitui a página de login
        self.mode = "auto"
        self.stats = Stats(started_at=time.monotonic())
        self.set_status(INICIANDO, f"início agendado em {atraso:g}s" if atraso else "abrindo a sessão")
        self.heartbeat = time.monotonic() + atraso
        self.task = asyncio.create_task(self._run(atraso), name=f"worker_{self.acc.folder}")

    async def stop(self):
        self.pending_start = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
            self.task = None
        await self._close_browser()
        self.login_open = False
        self.status, self.detail = OFFLINE, "parada"

    async def restart(self):
        """Fecha e reabre a sessão desta conta, mantendo as estatísticas."""
        self.log("reiniciando a conta")
        stats = self.stats
        await self.stop()
        self.start()
        stats.started_at = stats.started_at or self.stats.started_at
        self.stats = stats

    def pause(self):
        self.mode = "pausado"

    def take_manual(self):
        self.mode = "manual"

    def resume(self):
        self.mode = "auto"
        self.recheck = True
        self.log("automação retomada")

    async def open_login(self, url: str):
        """Login reserva: abre o jogo numa página comum, SEM monitoramento nem automação.
        Só para quando o login com a conta iniciada não funcionar."""
        if self.running:
            await self.stop()
        await self.browser.open_login_page(self.acc, url)
        self.login_open = True
        self.status, self.detail = AGUARDANDO, "faça o login na tela do jogo e depois clique em Iniciar"
        self.log("página de login sem automação aberta")

    # ------------------------------------------------------------ execução
    async def _run(self, atraso: float = 0):
        if atraso:
            await asyncio.sleep(atraso)
        backoff = 5
        while True:
            inicio = time.monotonic()
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except BrowserClosed as e:
                self.set_status(ERRO, str(e))
            except Exception as e:
                self.set_status(ERRO, _curto(e))
                self.log(f"erro: {_curto(e)}")
            finally:
                await self._close_browser()
            if not self.cfg["farm"]["reabrir_navegador"]:
                self.status, self.detail = OFFLINE, "parada após erro"
                return
            if time.monotonic() - inicio > 120:
                backoff = 5
            self.log(f"tentando reconectar em {backoff}s")
            self.heartbeat = time.monotonic() + backoff
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)

    async def _session(self):
        self.set_status(INICIANDO, "abrindo a sessão")
        self.heartbeat = time.monotonic()
        self.page = await self.browser.open_page(self.acc)
        fechou = asyncio.Event()
        self.page.on("close", lambda _p: fechou.set())
        self.page.on("Inspector.targetCrashed", lambda _p: fechou.set())
        self.game = GameSession(self.page, self._on_game_event)
        self.game.on_campo = self._on_campo
        self.farm = FarmRoutine(self)

        self.set_status(INICIANDO, "abrindo o PokeIdle")
        await self.page.goto(self.cfg["url"])
        self.log("sessão aberta")
        economia_em = 0.0
        while True:
            if fechou.is_set() or self.page.is_closed():
                raise BrowserClosed("a página da conta foi fechada ou travou")
            self.heartbeat = time.monotonic()
            inicio_passo = time.monotonic()
            try:
                if self.game.welcomed and time.monotonic() >= economia_em:
                    economia_em = time.monotonic() + 5
                    try:
                        await self.game.economia_segundo_plano(
                            self.browser.background and
                            self.cfg.get("desempenho", {}).get("economia_em_segundo_plano", True))
                    except Exception:
                        pass  # uma mudança visual do jogo não pode interromper o farm
                await self.farm.step()
                await self._avaliar_melhor_hunt()
            except Exception as e:
                if fechou.is_set() or self.page.is_closed():
                    raise BrowserClosed("a página da conta foi fechada ou travou")
                # Página recarregando no meio da leitura, elemento sumiu etc.: tenta de novo.
                self.detail = f"repetindo verificação ({_curto(e)})"
                await asyncio.sleep(2)
            if self.game.nick:
                self.stats.nick = self.game.nick
            if self.game.level is not None:
                self.stats.level = self.game.level
            ativo = self.game.active_pokemon
            self.stats.ativo_especie = ativo.get("speciesId") if ativo else None
            self.hunts.measure.on_pokemon_ativo(ativo)
            self.hunts.measure.tick()
            # Mercado: pede a vitrine dos itens ligados e marca as compras na liberação (rmt/rotina.py);
            # nada aqui mexe na tela do jogo nem espera resposta.
            await self.rmt.tick()
            # lido a cada volta: mudar nas Configurações vale na hora
            # Estado e estatísticas continuam chegando pelo socket. Um evento de batalha não
            # deve disparar outra leitura do DOM antes do intervalo configurado.
            intervalo = max(1, self.cfg["intervalos"]["verificacao_segundos"])
            await asyncio.sleep(max(0, intervalo - (time.monotonic() - inicio_passo)))

    async def _avaliar_melhor_hunt(self):
        """Reavalia com pouca frequência e nunca sobrepõe uma hunt fixada pela pessoa."""
        farm_cfg = self.cfg.get("farm", {})
        agora = time.monotonic()
        if (not farm_cfg.get("avancar_melhor_hunt", True) or self.acc.hunt or self.mode != "auto"
                or not self.game or not self.game.welcomed or not self.game.hunt_slug
                or self.game.in_battle or agora < self._melhor_hunt_em):
            return
        minutos = max(5, int(farm_cfg.get("reavaliar_hunt_minutos", 15)))
        self._melhor_hunt_em = agora + minutos * 60
        await self.hunts.refresh(self.game)
        escolha = recomendar_hunt_automatica(
            self.hunts.result, self.game.hunt_slug,
            farm_cfg.get("ganho_minimo_troca_pct", 5),
            farm_cfg.get("objetivo_hunt", "xp_pokemon"),
            farm_cfg.get("risco_maximo_hunt", "medio"),
            farm_cfg.get("usar_medicoes_reais", True))
        if not escolha:
            return
        ganho = escolha.get("_otimizador_ganho_pct")
        metrica = {"xp_pokemon": "XP do Pokémon/h", "xp_treinador": "XP do treinador/h",
                   "ouro": "ouro/h"}.get(escolha.get("_otimizador_objetivo"), "rendimento")
        fonte = "medição real + modelo" if escolha.get("_otimizador_medido") else "modelo"
        extra = f" (+{round(ganho)}% de {metrica}, {fonte})" if ganho is not None else f" ({fonte})"
        nome = self.game.hunt_name(escolha["slug"])
        self.log(f"melhor hunt segura: mudando para {nome}{extra}")
        await self.farm.go_hunt(escolha["slug"])

    def _on_campo(self, tipo: str, m: dict):
        if tipo == "campo.init":
            self.hunts.measure.on_campo_init(m)
        else:
            self.hunts.measure.on_campo(m)

    async def go_hunt(self, slug: str):
        """"Caçar aqui" do Hunt Analyzer: só navegação, pelo mesmo caminho do farm."""
        if not self.running or not self.game or not self.game.welcomed:
            self.log("Caçar aqui: inicie a conta primeiro")
            return
        nome = self.game.hunt_name(slug)
        self.log(f"Hunt Analyzer: indo para {nome}")
        self.last_action = f"entrar na hunt {nome}"
        if await self.game.enter_hunt(slug, self.cfg["url"]):
            self.remember_hunt(slug)
            self.log(f"agora caçando em {nome}")
        else:
            self.log(f"não consegui entrar em {nome} (área travada ou porta do mapa fechada)")

    async def _close_browser(self):
        if self.rmt.ligado:     # a lista de compras continua ligada e espera a conta voltar
            self.rmt.suspender("a sessão da conta foi fechada")
        self.hunts.measure.fechar_sessao()
        page, self.page, self.game = self.page, None, None
        try:
            await asyncio.wait_for(self.browser.close_page(self.acc, page), 15)
        except Exception:
            pass

    # -------------------------------------------------------- eventos do jogo
    def _on_game_event(self, tipo: str, d: dict):
        s = self.stats
        batalhas = self.cfg["farm"]["log_cada_batalha"]
        if tipo == "batalha_inicio":
            if batalhas:
                alvo = f" contra {d['nome']} Nv{d['level']}" if d.get("nome") else ""
                self.log(f"batalha iniciada{alvo}")
        elif tipo == "batalha_fim":
            s.battles += 1
            xp = int(d.get("xp") or 0)
            s.xp_gained += xp
            self.hunts.measure.on_xp(xp)
            res = d.get("resultado")
            texto = {"capturado": f"capturou {d.get('nome')}", "fugiu": f"{d.get('nome')} fugiu"}.get(
                res, f"vitória +{xp:,} XP".replace(",", "."))
            s.last_battle = f"{time.strftime('%H:%M:%S')} {texto}"
            if batalhas:
                self.log(f"batalha concluída ({texto})")
        elif tipo == "xp_extra":
            # Outro selvagem da mesma onda derrotado: soma na mesma batalha.
            s.xp_gained += int(d.get("xp") or 0)
            self.hunts.measure.on_xp(int(d.get("xp") or 0))
        elif tipo == "centro" and d.get("motivo") == "morte":
            s.defeats += 1
            if self.farm:
                self.farm.register_defeat()
            self.log("time nocauteado - foi para o Centro Pokémon")
        elif tipo == "xp_perdido":
            s.xp_gained -= int(d.get("qtd") or 0)
            self.log(f"perdeu {d.get('qtd')} XP de treinador no nocaute")
        elif tipo == "level_treinador":
            s.level = d.get("level")
            self.log(f"treinador subiu para o nível {d.get('level')}")
        elif tipo == "conectado":
            self.log(f"conectado ao servidor como {self.game.nick if self.game else '?'}")
            if self.game:
                self.hunts.measure.on_welcome(self.game.welcome_data.get("hunts"))
                ident = {"nick": self.game.nick, "id": self.game.eu.get("id")}
                if ident["id"] is not None and ident != self.identidade:
                    self.identidade = ident
                    self._save_state(**ident)
        elif tipo == "desconectado":
            if self.running:
                self.log("conexão perdida - o jogo está tentando reconectar")
        elif tipo == "erro_conta":
            self.log(f"servidor recusou a conta: {d.get('texto')}")
        elif tipo == "sem_itens":
            self.log("sem poção e sem revive - o jogo pausou a volta automática")
