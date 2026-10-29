"""Gerencia os workers das contas.

Roda um loop asyncio numa thread separada da interface. Cada conta é uma tarefa
independente nesse loop, com a sua própria página embutida (e o seu processo de
renderização): todas andam ao mesmo tempo, e o erro de uma não para as outras.
"""
import asyncio
import queue
import threading
import time
from collections import Counter
from datetime import datetime

from app.config import LOGS_DIR, Account
from browser.browser_manager import BrowserManager
from browser.proc_mem import memoria_privada_mb
from browser.web_host import WebHost
from hunts.game_data import GameData
from workers.account_worker import AccountWorker
from workers.farm_worker import FARMING

WATCHDOG_SEGUNDOS = 150   # sem "batimento" por esse tempo = worker travado
MEMORIA_MINUTOS = 5       # acima do limite de memória por esse tempo = reabre a página
MEMORIA_INTERVALO_MIN = 30  # no máximo uma reabertura por memória a cada 30 min por conta


class Manager:
    def __init__(self, cfg: dict, accounts: list[Account], web: WebHost):
        self.cfg = cfg
        self.accounts = accounts
        self.web = web
        self.logs: queue.Queue[str] = queue.Queue(maxsize=4000)
        self._reservas = Counter()
        self._reserva_lock = threading.RLock()
        self._comandos: dict[int, asyncio.Lock] = {}
        self._log_dia = None
        self._log_arq = None
        self._log_trava = threading.Lock()
        self._acima_desde: dict[int, float] = {}       # conta -> desde quando passou do limite
        self._reaberta_em: dict[int, float] = {}
        self.browser = BrowserManager(web, zoom=cfg["janela"]["zoom"])
        # Catálogo e fórmulas do jogo para o Hunt Analyzer (iguais para todas as contas; os dados
        # de cada conta ficam no analisador dela).
        self.hunt_data = GameData(web)
        self.workers = [AccountWorker(a, cfg, self.browser, self._log, self.hunt_data, self.contas_proprias)
                        for a in accounts]
        self.selected = 0
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._thread_main, name="manager-loop", daemon=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- loop
    def start(self):
        self._thread.start()

    def _thread_main(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._watchdog())
        self.loop.run_forever()
        self.loop.close()

    def _call(self, fn, *args):
        """Agenda algo no loop dos workers a partir da interface."""
        async def runner():
            r = fn(*args)
            if asyncio.iscoroutine(r):
                await r
        fut = asyncio.run_coroutine_threadsafe(runner(), self.loop)
        fut.add_done_callback(self._report_error)
        return fut

    def _report_error(self, fut):
        if not fut.cancelled() and fut.exception():
            self._log(None, f"erro interno: {fut.exception()}")

    # ------------------------------------------------------------- comandos
    def _comando_conta(self, i, fn, *args, reservar=False):
        """Serializa abrir/parar/reiniciar por conta e reserva a vaga antes de sair da UI."""
        if reservar:
            with self._reserva_lock:
                self._reservas[i] += 1

        async def executar():
            try:
                async with self._comandos.setdefault(i, asyncio.Lock()):
                    retorno = fn(*args)
                    if asyncio.iscoroutine(retorno):
                        await retorno
            finally:
                if reservar:
                    with self._reserva_lock:
                        self._reservas[i] -= 1
        return self._call(executar)

    def connected_count(self, excluding: int | None = None) -> int:
        with self._reserva_lock:
            return sum(1 for w in self.workers if w.acc.index != excluding and
                       (w.running or w.pending_start or w.login_open or self._reservas[w.acc.index]))

    def can_connect(self, i: int) -> tuple[bool, str]:
        w = self.workers[i]
        if not w.acc.enabled:
            return False, f"{w.acc.name} está desativada no config.toml (ativa = false)."
        limite = self.cfg["max_simultaneas"]
        if self.connected_count(excluding=i) >= limite:
            return False, (f"O limite local é {limite} sessões. Pare uma conta ou ajuste "
                           "'Máximo conectadas ao mesmo tempo'. O servidor tem limites próprios.")
        return True, ""

    def start_account(self, i: int, atraso: float = 0) -> tuple[bool, str]:
        with self._reserva_lock:
            if self.workers[i].running or self._reservas[i]:
                return True, ""
            return self._iniciar_conta(i, atraso)

    def _iniciar_conta(self, i: int, atraso: float) -> tuple[bool, str]:
        ok, motivo = self.can_connect(i)
        if not ok:
            self._log(i, f"não iniciada: {motivo}")
            return False, motivo
        self._log(i, "iniciando")
        self._comando_conta(i, self.workers[i].start, atraso, reservar=True)
        return True, ""

    def start_all(self):
        ordem = 0
        for w in self.workers:
            if w.acc.enabled and not w.running and not self._reservas[w.acc.index]:
                if not self.start_account(w.acc.index, ordem * self.cfg.get("intervalo_inicio_segundos", 3))[0]:
                    break
                ordem += 1

    def stop_account(self, i: int):
        self._log(i, "parando")
        self._comando_conta(i, self.workers[i].stop)

    def stop_all(self):
        for w in self.workers:
            if w.running or w.pending_start or w.login_open or self._reservas[w.acc.index]:
                self.stop_account(w.acc.index)

    def restart_account(self, i: int):
        if not self.workers[i].running:
            return self.start_account(i)
        self._comando_conta(i, self.workers[i].restart, reservar=True)

    def set_background(self, ativo: bool):
        self.browser.background = ativo

    def pause(self, i: int):
        self._log(i, "automação pausada")
        self._call(self.workers[i].pause)

    def resume(self, i: int):
        self._call(self.workers[i].resume)

    def take_manual(self, i: int):
        self._log(i, "modo manual - a automação desta conta parou, as outras continuam")
        self._call(self.workers[i].take_manual)

    # ------------------------------------------------------- Hunt Analyzer
    def hunt_refresh(self, i: int, force: bool = False):
        """Pede (sem bloquear a tela) a análise da conta i. Só recalcula se algo mudou."""
        w = self.workers[i]
        if not w.hunts.busy:
            self._call(w.hunts.refresh, w.game, force)

    def hunt_view(self, i: int) -> dict:
        w = self.workers[i]
        return w.hunts.view(w.game)

    def hunt_set_pref(self, i: int, chave: str, valor):
        self.workers[i].hunts.set_pref(chave, valor)

    def go_hunt(self, i: int, slug: str):
        self._call(self.workers[i].go_hunt, slug)

    # -------------------------------------------------------------- Pokédex
    def pokedex_catalogo(self):
        """Só leitura, para a Pokédex: o catálogo de espécies da versão no ar (o mesmo do Hunt Analyzer, pela
        página de dados sem conta). Não bloqueia a tela: devolve um Future."""
        fut = asyncio.run_coroutine_threadsafe(self.hunt_data.garantir(), self.loop)
        fut.add_done_callback(self._report_error)
        return fut

    # ------------------------------------------------------------- RMT
    def contas_proprias(self) -> set:
        """Nicks (minúsculos) e ids no jogo de TODAS as contas do PokeNexus — o RMT nunca compra
        anúncio delas (com o bloqueio ligado) nem as conta como concorrência."""
        out = set()
        for w in self.workers:
            ids = [w.identidade]
            if w.game:
                ids.append({"nick": w.game.nick, "id": w.game.eu.get("id")})
            for x in ids:
                if x.get("nick"):
                    out.add(str(x["nick"]).strip().lower())
                if x.get("id") is not None:
                    out.add(x["id"])
        return out

    def rmt_view(self, i: int) -> dict:
        return self.workers[i].rmt.view()

    def rmt_parar_todos(self):
        for w in self.workers:
            if w.rmt.ligado:
                w.rmt.parar("você clicou em Parar todas as compras")

    def open_login(self, i: int) -> tuple[bool, str]:
        with self._reserva_lock:
            w = self.workers[i]
            if w.login_open or self._reservas[i]:
                return False, "A página desta conta já está aberta ou iniciando."
            ok, motivo = self.can_connect(i)
            if not ok:
                return False, motivo
            self._comando_conta(i, w.open_login, self.cfg["url"], reservar=True)
        return True, ""

    def shutdown(self):
        """Para todas as contas e encerra o loop. Chamado pela interface, que depois fecha
        as páginas (WebHost.close_all) — por isso os workers não esperam por ela aqui."""
        self.browser.shutting_down = True

        async def _all():
            pendentes = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in pendentes:
                t.cancel()
            await asyncio.gather(*pendentes, return_exceptions=True)
            await asyncio.gather(*(w.stop() for w in self.workers), return_exceptions=True)
        if not self._thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(_all(), self.loop).result(timeout=45)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
        with self._log_trava:
            if self._log_arq:
                self._log_arq.close()
                self._log_arq = None

    # ---------------------------------------------------------------- dados
    def snapshot(self) -> list[dict]:
        out = []
        for w in self.workers:
            s = w.stats
            out.append({
                "index": w.acc.index, "name": w.acc.name, "enabled": w.acc.enabled,
                "sprite": w.acc.sprite, "status": w.status, "detail": w.detail,
                "mode": w.mode, "running": w.running or bool(self._reservas[w.acc.index]), "login_open": w.login_open,
                "level": s.level, "nick": s.nick, "xp_gained": s.xp_gained if s.battles else None,
                "xp_h": s.xp_per_hour, "elapsed": s.elapsed if w.running else 0,
                "battles": s.battles, "last_battle": s.last_battle, "last_action": w.last_action,
                "ativo_especie": s.ativo_especie if w.running else None,
                "hunt": w.game.hunt_name(w.game.hunt_slug) if w.game and w.game.hunt_slug else
                        (w.last_hunt or "-"),
            })
        return out

    def _log(self, i: int | None, msg: str):
        quem = self.accounts[i].name if i is not None else "Sistema"
        line = f"[{datetime.now():%H:%M:%S}] {quem} - {msg}"
        try:
            self.logs.put_nowait(line)
        except queue.Full:
            try:
                self.logs.get_nowait()
            except queue.Empty:
                pass
            try:
                self.logs.put_nowait(line)
            except queue.Full:
                pass             # o arquivo em disco continua recebendo todas as linhas
        with self._log_trava:      # a tela e o loop das contas escrevem no log
            try:
                # Um arquivo por dia, aberto uma vez (e não a cada linha do log).
                dia = f"{datetime.now():%Y-%m-%d}"
                if dia != self._log_dia or self._log_arq is None:
                    if self._log_arq:
                        self._log_arq.close()
                    self._log_arq = open(LOGS_DIR / f"{dia}.log", "a", encoding="utf-8")
                    self._log_dia = dia
                self._log_arq.write(line + "\n")
                self._log_arq.flush()
            except OSError:
                self._log_arq = None
        if i is not None:
            w = self.workers[i] if i < len(getattr(self, "workers", [])) else None
            if w and not msg.startswith("batalha"):
                w.last_action = msg

    # ------------------------------------------------------------- vigias
    async def _watchdog(self):
        voltas = 0
        while True:
            await asyncio.sleep(10)
            for w in self.workers:
                if w.running and time.monotonic() - w.heartbeat > WATCHDOG_SEGUNDOS:
                    self._log(w.acc.index, "worker travado - reiniciando só esta conta")
                    w.heartbeat = time.monotonic()
                    self.restart_account(w.acc.index)
            voltas += 1
            # Memória a cada 10 s: reabrir só vale entre uma batalha e outra (FARMING), e numa
            # hunt cheia essa janela é curta — olhar de minuto em minuto quase nunca a pegava.
            self._vigiar_memoria()
            if voltas % 6 == 0:
                try:
                    await self.hunt_data.fechar_se_ociosa()
                except Exception:
                    pass

    def _vigiar_memoria(self):
        """A página do jogo vai acumulando memória com as horas. Se a de uma conta ficar acima
        do limite por alguns minutos, ela é reaberta (o mesmo caminho do "reiniciar" da conta),
        só no farm automático e entre uma batalha e outra; as outras contas não são tocadas."""
        limite = self.cfg["farm"].get("limite_memoria_pagina_mb") or 0
        if limite <= 0:
            return
        agora = time.monotonic()
        # Quem está há mais tempo acima do limite é atendido primeiro (nenhuma conta fica esperando).
        for w in sorted(self.workers, key=lambda w: self._acima_desde.get(w.acc.index, agora)):
            i = w.acc.index
            mb = memoria_privada_mb(self.web.pids.get(i)) if w.running else None
            if mb is None or mb < limite:
                self._acima_desde.pop(i, None)
                continue
            desde = self._acima_desde.setdefault(i, agora)
            if (agora - desde < MEMORIA_MINUTOS * 60 or w.mode != "auto" or w.status != FARMING
                    or agora - self._reaberta_em.get(i, -1e9) < MEMORIA_INTERVALO_MIN * 60):
                continue
            self._acima_desde.pop(i, None)
            self._reaberta_em[i] = agora
            self._log(i, f"página usando {mb:,.0f} MB (limite {limite:,} MB) - reabrindo só esta conta "
                         f"para liberar memória".replace(",", "."))
            w.heartbeat = agora
            self.restart_account(i)
            return                         # uma conta por vez
