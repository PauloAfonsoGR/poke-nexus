"""Tudo que é específico do PokeIdle.

Como o jogo funciona (lido do app.js 1.279.2):
- O login fica no LocalStorage, chave "sessao" = {nick, token}; vale 30 dias e o
  servidor renova sozinho. Não há cookie de login.
- Depois de carregar, a página abre um WebSocket (wss://pokeidle.io) e manda
  "hello" com o token. O servidor responde "welcome" (estado completo) e depois
  manda "estado" (só os campos que mudaram) e "batalha" (eventos de luta).
- O farm é do SERVIDOR: escolhida uma área (hunt), as lutas acontecem sozinhas:
  spawn -> ataque... -> morte (selvagem derrotado, com XP) -> próximo spawn.
- Se o time cai, vem o evento "centro" (motivo "morte") e o jogador vai para o
  Centro Pokémon (estado.noCentro = true) e perde um pouco de XP ("xpPerdido").

Este módulo só ESCUTA o WebSocket (pelos eventos Network.* do DevTools, sem injetar
nada na página) e usa o DOM para as poucas ações necessárias.
"""
import asyncio
import json
import time

from browser.cdp import CdpPage
from game import selectors as S
from game.economia import JS_ECONOMIA

# Campos do estado tratados à parte: a coleção de pokémon chega em pedaços (pkMud/pkFora) e a
# Pokédex também (dexMud/dexFora): ela fica só em `self.dex`, para a Pokédex do PokeNexus ler.
_IGNORAR = {"pokemons", "pkMud", "pkFora", "dexMud", "dexFora", "pokedex", "cheio"}

# Tipos de mensagem do servidor que o PokeNexus usa (os demais — chat, ranking... — são ignorados).
_USADOS = {"welcome", "estado", "batalha", "erro", "campo.init", "campo", "market"}

# Campos de cada pokémon que o PokeNexus usa (a coleção chega com ~200 por conta).
_CAMPOS_POKEMON = ("id", "speciesId", "nome", "level", "stats", "ivs", "maxHp", "tipos", "tmElemental",
                   "tmAoe", "tm_aoe", "quality", "qualidade", "potencia", "refino")

# O que o Hunt Analyzer usa do `welcome` (catálogo de hunts e constantes do servidor).
_WELCOME_HUNT = ("hunts", "tabelaTipos", "ampliacaoHunt", "multHpSelvagem", "multDanoSelvagem",
                 "tiposBoost", "itensNossos")

# Erros do servidor que travam a conta (ver ALERTAS_DO_SOCKET no app.js).
ERROS_DE_CONTA = {
    "auth.sessaoInvalida": "sessão inválida",
    "auth.precisaLogin": "precisa fazer login",
    "auth.contaExcluida": "conta excluída",
    "auth.contaBanida": "conta banida",
    "auth.ipBanido": "rede banida",
    "auth.provedorBanido": "provedor de rede bloqueado pelo servidor",
    "login.contaBanida": "conta banida",
    "login.ipBanido": "rede banida",
    "login.limiteOnlineIp": "limite de contas conectadas nesta rede",
    "login.limiteOnlineIpLista": "limite de contas conectadas nesta rede",
    "login.limiteContasIp": "limite de contas criadas nesta rede",
}
ERROS_DE_SESSAO = {"auth.sessaoInvalida", "auth.precisaLogin"}
ERROS_LIMITE_REDE = {"login.limiteOnlineIp", "login.limiteOnlineIpLista", "login.limiteContasIp"}


def diagnostico_recusa(chave: str) -> str:
    texto = ERROS_DE_CONTA.get(chave, chave)
    if chave in ERROS_LIMITE_REDE:
        return (f"{texto} ({chave}). Limite do servidor por IP/rede; aumentar o limite local "
                "não libera vagas. Libere uma sessão ou consulte o suporte sobre liberação da rede.")
    return texto


class GameSession:
    """Estado de UMA conta, montado a partir das mensagens do servidor."""

    def __init__(self, page: CdpPage, on_event):
        self.page = page
        self.on_event = on_event          # callback(tipo: str, dados: dict)
        self.eu: dict = {}                # estado do jogador (campos de topo)
        self.pokemons: dict = {}          # id -> pokémon da conta (com stats calculados pelo servidor)
        self.hunts: dict[str, str] = {}   # slug -> nome da área
        self.hunt_regiao: dict[str, str] = {}   # slug -> região do Mapa (cada região é uma tela)
        self.welcome_data: dict = {}      # hunts + constantes do servidor (Hunt Analyzer)
        self.welcome_seq = 0              # muda a cada welcome (catálogo de hunts novo)
        self.on_campo = None              # callback(tipo, msg) das mensagens campo.init/campo
        # RMT (Mercado da Comunidade): o que o servidor responde quando a TELA do jogo pede.
        self.mercado_info: dict = {}      # welcome.mercado: catálogo de itens negociáveis, mínimos
        self.economia: dict = {}          # welcome.economia: taxa do mercado em ouro, preço da gema
        self.mercado: dict = {}           # aba -> última resposta (item: por "itemId:moeda")
        self.mercado_seq = 0              # sobe a cada resposta do mercado
        self.mercado_evento = asyncio.Event()
        self.mercado_eventos: list[tuple[float, dict]] = []   # eventos market* (comprou, vendeu...)
        # Pokédex do jogo, só para a Pokédex do PokeNexus ler (game/pokedex.py): {chave: {k, c, sv, sc}}, com
        # a mesma regra do jogo (shared/estado-delta.mjs: inteira no welcome/cheio, dexMud entra, dexFora sai).
        self.dex: dict = {}
        self.dex_seq = 0                  # sobe a cada mudança (a tela só olha quando ele muda)
        self.dex_capturas: list = []      # speciesId do evento de batalha "capturado" (os últimos 50)
        self.ultimo_erro: tuple[float, str, dict] | None = None   # (monotonic, chave, params)
        # Recusas e avisos recentes (erro do servidor, ou o aviso "market.*" do sorteio da liberação):
        # [(monotonic, chave, params)], os últimos 40. O Mercado confere o resultado de uma compra aqui.
        self.avisos: list[tuple[float, str, dict]] = []
        self.ws_open = False
        self.welcomed = False
        self.last_msg_at = time.monotonic()
        self.last_battle_event_at = time.monotonic()
        self.in_battle = False
        self.error_key: str | None = None
        self.changed = asyncio.Event()
        self._ws_ids: set[str] = set()
        # Uma "batalha" = uma onda de selvagens. Uma onda pode ter vários selvagens: um cai,
        # outro escapa... e conta como UMA batalha (ver _start_battle/_resolve).
        self._wave = None                 # último estado.ondaSeq visto
        self._last_spawn_at = None
        self._last_resolved_at = -1e9
        # Travas de troca de hunt do jogo: 3 s sem trocar dano e a porta de 10 s do Mapa.
        self._combate_ate = 0.0           # time.monotonic()
        self._porta_srv = 0               # ms no relógio do servidor
        self._srv = None                  # (servidorAgora, time.monotonic()) do último estado
        page.on("Network.webSocketCreated", self._on_ws_created)
        page.on("Network.webSocketFrameReceived", self._on_ws_frame)
        page.on("Network.webSocketClosed", self._on_ws_closed)

    # ------------------------------------------------------------ WebSocket
    def _on_ws_created(self, p: dict):
        if "pokeidle.io" not in p.get("url", ""):
            return
        self._ws_ids.add(p["requestId"])
        self.ws_open = True
        self.last_msg_at = time.monotonic()

    def _on_ws_frame(self, p: dict):
        resp = p.get("response") or {}
        if p.get("requestId") in self._ws_ids and resp.get("opcode") == 1:
            self._on_frame(resp.get("payloadData", ""))

    def _on_ws_closed(self, p: dict):
        if p.get("requestId") in self._ws_ids:
            self._ws_ids.discard(p["requestId"])
            self._on_close()

    def _on_close(self):
        self.ws_open = False
        self.welcomed = False
        self.on_event("desconectado", {})
        self.changed.set()

    def _on_frame(self, payload):
        if not isinstance(payload, str):
            return
        self.last_msg_at = time.monotonic()            # qualquer mensagem prova que a conexão vive
        # O tipo vem no começo ({"t":"chat",...}): os tipos que ninguém usa nem são interpretados.
        i = payload.find('"t":"', 0, 40)
        if i >= 0 and payload[i + 5:payload.find('"', i + 5)] not in _USADOS:
            return
        try:
            m = json.loads(payload)
        except ValueError:
            return
        t = m.get("t")
        if t == "welcome":
            self.welcomed = True
            self.error_key = None
            self.in_battle = False
            self.last_battle_event_at = time.monotonic()
            estado = m.get("estado") or {}
            self.eu = {k: v for k, v in estado.items() if k not in _IGNORAR}
            self._merge_pokemons({**estado, "cheio": True})
            self._merge_dex({**estado, "cheio": True})
            self._wave = self.eu.get("ondaSeq")
            for h in m.get("hunts") or []:
                if isinstance(h, dict) and h.get("slug"):
                    self.hunts[h["slug"]] = str(h.get("nome") or h.get("name") or h["slug"])
                    self.hunt_regiao[h["slug"]] = h.get("regiao") or h.get("area")
            self.welcome_data = {k: m.get(k) for k in _WELCOME_HUNT}
            self.mercado_info = m.get("mercado") or {}
            self.economia = m.get("economia") or {}
            self.welcome_seq += 1
            self.on_event("conectado", {})
            self.changed.set()
        elif t == "estado":
            parcial = m.get("estado") or {}
            if parcial.get("cheio"):
                self.eu = {}
            self.eu.update({k: v for k, v in parcial.items() if k not in _IGNORAR})
            if parcial.get("servidorAgora"):
                self._srv = (parcial["servidorAgora"], time.monotonic())
            self._merge_pokemons(parcial)
            self._merge_dex(parcial)
            self._check_new_wave()
            self.changed.set()
        elif t in ("campo.init", "campo"):
            if self.on_campo:
                self.on_campo(t, m)
        elif t == "batalha":
            for e in m.get("ev") or []:
                self._on_battle_event(e)
        elif t == "market":
            aba = m.get("aba") or "vitrine"
            self.mercado_seq += 1
            m["_seq"] = self.mercado_seq          # quem espera uma resposta só aceita as novas
            if aba == "item":
                self.mercado[f"item:{m.get('itemId')}:{m.get('moeda')}"] = m
            self.mercado[aba] = m
            self.mercado_evento.set()
        elif t == "erro":
            chave = m.get("chave") or ""
            self.ultimo_erro = (time.monotonic(), chave or str(m.get("msg") or ""), m.get("params") or {})
            self._avisar(*self.ultimo_erro)
            if chave in ERROS_DE_CONTA:
                self.error_key = chave
                self.on_event("erro_conta", {"chave": chave, "texto": ERROS_DE_CONTA[chave]})
                self.changed.set()

    def _merge_pokemons(self, parcial: dict):
        """A coleção de pokémon em delta, com a mesma regra do jogo (shared/estado-delta.mjs):
        `cheio` recomeça; uma lista completa substitui; pkMud atualiza; pkFora remove."""
        enxuto = lambda p: {k: p[k] for k in _CAMPOS_POKEMON if k in p}
        lista = parcial.get("pokemons")
        if parcial.get("cheio") or lista is not None:
            self.pokemons = {p["id"]: enxuto(p) for p in lista or [] if isinstance(p, dict) and "id" in p}
        for p in parcial.get("pkMud") or []:
            if isinstance(p, dict) and "id" in p:
                self.pokemons[p["id"]] = enxuto(p)
        for pid in parcial.get("pkFora") or []:
            self.pokemons.pop(pid, None)

    def _merge_dex(self, parcial: dict):
        """A Pokédex do jogo em delta (shared/estado-delta.mjs): `cheio` ou a Pokédex inteira recomeçam;
        dexMud entra/troca; dexFora sai. Só guarda: quem lê é a Pokédex do PokeNexus."""
        mud, fora = parcial.get("dexMud"), parcial.get("dexFora")
        if parcial.get("cheio") or "pokedex" in parcial:
            self.dex = dict(parcial.get("pokedex") or {})
        elif not mud and not fora:
            return
        if isinstance(mud, dict):
            self.dex.update(mud)
        for chave in fora or []:
            self.dex.pop(chave, None)
            self.dex.pop(str(chave), None)
        self.dex_seq += 1

    @property
    def active_pokemon(self) -> dict | None:
        return self.pokemons.get(self.eu.get("activeId"))

    def _check_new_wave(self):
        # O número da onda chega no pacote de estado, DEPOIS dos eventos do mesmo tique. Ele só
        # marca o início de uma batalha quando o jogo não está mandando `spawn` (reserva).
        onda = self.eu.get("ondaSeq")
        if isinstance(onda, int) and onda != self._wave:
            self._wave = onda
            sem_spawn = self._last_spawn_at is None or time.monotonic() - self._last_spawn_at > 10
            if onda > 0 and sem_spawn and self.hunt_slug and not self.no_centro:
                self._start_battle({})

    def _start_battle(self, info: dict):
        if not self.in_battle:
            self.in_battle = True
            self.on_event("batalha_inicio", info)

    def _resolve(self, dados: dict):
        """Resultado de um selvagem. O primeiro resultado da batalha em andamento a conclui; os
        seguintes (outro selvagem da mesma onda) só somam o XP. Um resultado sem batalha em
        andamento e longe do último (ex.: conectou no meio de uma onda) conta como batalha."""
        agora = time.monotonic()
        if self.in_battle or agora - self._last_resolved_at > 3:
            self.in_battle = False
            self._last_resolved_at = agora
            self.on_event("batalha_fim", dados)
        elif dados.get("xp"):
            self.on_event("xp_extra", dados)

    def _avisar(self, quando: float, chave: str, params: dict):
        self.avisos.append((quando, chave, params))
        del self.avisos[:-40]
        self.mercado_evento.set()

    def agora_servidor_ms(self) -> float:
        """Agora no relógio do SERVIDOR (o mesmo que o jogo usa para a retenção dos anúncios)."""
        if self._srv:
            return self._srv[0] + (time.monotonic() - self._srv[1]) * 1000
        return time.time() * 1000

    def _on_battle_event(self, e: dict):
        k = e.get("k")
        if k == "aviso" and str(e.get("msg") or "").startswith("market"):
            # o sorteio da liberação ("entrou no sorteio", "outro jogador levou") chega como aviso
            self._avisar(time.monotonic(), str(e["msg"]), e.get("params") or {})
            return
        if isinstance(k, str) and k.startswith("market"):
            # Resultado do Mercado da Comunidade (comprou, anunciou, vendeu...): não é batalha, então
            # não mexe no relógio da vigia de "nenhuma batalha".
            self.mercado_eventos.append((time.monotonic(), e))
            del self.mercado_eventos[:-50]
            self.mercado_evento.set()
            self.on_event("mercado", e)
            return
        self.last_battle_event_at = time.monotonic()
        if k == "ataque":
            # Dano trocado rearma os 3 s da saída da hunt (a mesma regra do jogo, `rearmarCombate`).
            self._combate_ate = time.monotonic() + 3.0
        elif k == "hunt" and e.get("trocaLivreEm"):
            self._porta_srv = e["trocaLivreEm"]          # porta do Mapa (relógio do servidor)
        if k == "spawn":
            self._last_spawn_at = time.monotonic()
            self._start_battle({"nome": e.get("nome"), "level": e.get("level")})
        elif k == "morte":
            if e.get("quem") == "selvagem":
                xp = e.get("xpTreinador", e.get("xp")) or 0
                self._resolve({"xp": xp, "ouro": e.get("ouro") or 0, "nome": e.get("nome")})
            else:
                self.on_event("pokemon_desmaiou", {})
        elif k in ("fugiu", "capturado"):
            nome = (e.get("pokemon") or {}).get("nome") if k == "capturado" else e.get("nome")
            self._resolve({"xp": 0, "resultado": k, "nome": nome})
            if k == "capturado" and (e.get("pokemon") or {}).get("speciesId") is not None:
                self.dex_capturas.append(e["pokemon"]["speciesId"])     # a Pokédex do PokeNexus, na hora
                del self.dex_capturas[:-50]
                self.dex_seq += 1
        elif k == "centro":
            self.in_battle = False
            self.on_event("centro", {"motivo": e.get("motivo")})
        elif k == "xpPerdido":
            self.on_event("xp_perdido", {"qtd": e.get("qtd") or 0})
        elif k == "levelup" and e.get("quem") == "treinador":
            self.on_event("level_treinador", {"level": e.get("level")})
        elif k == "autoHuntSemItens":
            self.on_event("sem_itens", {})
        self.changed.set()

    # --------------------------------------------------------------- leitura
    @property
    def nick(self) -> str | None:
        return self.eu.get("nick")

    @property
    def level(self) -> int | None:
        v = self.eu.get("level")
        return int(v) if isinstance(v, (int, float)) else None

    @property
    def xp(self) -> int | None:
        v = self.eu.get("xp")
        return int(v) if isinstance(v, (int, float)) else None

    @property
    def hunt_slug(self) -> str | None:
        return self.eu.get("huntSlug") or None

    @property
    def no_centro(self) -> bool:
        return bool(self.eu.get("noCentro"))

    @property
    def em_outra_cena(self) -> str | None:
        """Boss, arena mística ou casa: lugares onde o programa não mexe."""
        if (self.eu.get("boss") or {}).get("arena"):
            return "boss"
        if self.eu.get("mistico"):
            return "arena mística"
        if (self.eu.get("casa") or {}).get("dentro"):
            return "casa"
        return None

    @property
    def auto_voltar_hunt(self) -> bool:
        return bool((self.eu.get("automation") or {}).get("autoVoltarHunt"))

    def hunt_name(self, slug: str | None) -> str:
        return self.hunts.get(slug, slug) if slug else "-"

    async def read_screen(self) -> dict:
        return await self.page.evaluate(S.JS_LER_TELA)

    async def wait_change(self, timeout: float):
        """Espera uma mensagem nova do servidor (ou o tempo acabar)."""
        self.changed.clear()
        try:
            await asyncio.wait_for(self.changed.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    # ---------------------------------------------------------------- ações
    async def economia_segundo_plano(self, ativo: bool):
        return await self.page.evaluate(JS_ECONOMIA, ativo, timeout=5)

    async def click_reload_version(self):
        await self.page.click(S.BTN_RECARREGAR_VERSAO, timeout=5)

    async def heal(self) -> bool:
        """Clica em "Curar equipe" no Centro Pokémon, se o botão estiver à vista."""
        for sel in (S.BTN_CURAR_CENTRO, S.BTN_CURAR_ECO):
            if await self.page.is_visible(sel):
                await self.page.click(sel, timeout=5)
                return True
        return False

    def troca_livre_em(self) -> float:
        """Segundos até o jogo deixar trocar de área pelo Mapa (0 = já pode). São as duas travas
        do jogo, que valem também no servidor: 3 s sem trocar dano (`centroLivreEm`, rearmada a
        cada golpe) e a porta de 10 s depois de entrar numa área (`trocaLivreEm`)."""
        agora = time.monotonic()
        na_hunt = bool(self.hunt_slug) and not self.no_centro
        resta = max(0.0, self._combate_ate - agora) if na_hunt else 0.0
        if self._srv:
            srv_agora = self._srv[0] + (agora - self._srv[1]) * 1000
            for carimbo in ((self.eu.get("centroLivreEm") or 0) if na_hunt else 0, self._porta_srv):
                if carimbo:
                    resta = max(resta, (carimbo - srv_agora) / 1000)
        return resta

    def porta_livre_em(self) -> float:
        """Segundos até abrir a porta de 10 s do Mapa depois de entrar numa área (0 = aberta)."""
        if not (self._srv and self._porta_srv):
            return 0.0
        srv_agora = self._srv[0] + (time.monotonic() - self._srv[1]) * 1000
        return max(0.0, (self._porta_srv - srv_agora) / 1000)

    async def enter_hunt(self, slug: str, base_url: str, timeout: float = 90) -> bool:
        """Entra na área `slug` pelo Mapa do jogo, como um jogador: espera a janela em que o jogo
        deixa trocar (sem combate e com a porta aberta), clica no marcador e confere pelo estado;
        se o jogo recusar, tenta na próxima janela. O atalho oficial `?hunt=<slug>` (que recarrega
        a página) só é usado quando a conta NÃO está numa hunt e o Mapa não tem o marcador."""
        marcador = S.MARCADOR_HUNT.format(slug=slug)
        chegou = lambda: self.hunt_slug == slug and not self.no_centro
        fim = time.monotonic() + timeout
        sem_marcador = False
        while time.monotonic() < fim:
            if chegou():
                return True
            porta = self.porta_livre_em()
            if porta > 0:
                await asyncio.sleep(min(porta + 0.15, 1.0))
                continue
            try:
                if not await self.page.exists(marcador):
                    if not await self.page.exists(S.MAPA_REGIAO_QUALQUER):
                        await self.page.click_presente(S.BTN_MAPA, timeout=5)
                        await self.page.wait_for(S.MAPA_REGIAO_QUALQUER, timeout=8, visible=False)
                    # O Mapa mostra UMA região por vez: a área de outra região só aparece depois
                    # de escolher a região dela (o mesmo botão que o jogador clica).
                    if not await self.page.exists(marcador):
                        await self._procurar_no_mapa(slug, marcador)
                    await self.page.wait_for(marcador, timeout=8, visible=False)
                if await self.page.get_attribute(marcador, "data-travado") == "1":
                    return False                       # nível de treinador insuficiente
                # A trava de combate é a do PRÓPRIO jogo: o botão "Ir para o Centro" fica
                # desligado enquanto ela vale e liga na janela livre (entre ondas, ou antes do
                # primeiro golpe da onda nova). Conferir e clicar no mesmo instante.
                r = await self.page.evaluate(S.JS_CLICAR_SE_LIVRE, marcador)
            except Exception:
                sem_marcador = True
                break
            if r in ("travado", "ficha"):
                await asyncio.sleep(0.15 if r == "travado" else 0.4)
                continue
            if r != "ok":
                sem_marcador = True
                break
            if await self._wait_for(chegou, 3):
                return True
            # Recusado (um golpe chegou no mesmo instante): tenta na próxima janela livre.
        if chegou():
            return True
        if sem_marcador and not self.hunt_slug:
            await self.page.goto(f"{base_url}?hunt={slug}")
            return await self._wait_for(chegou, 30)
        try:
            if await self.page.is_visible(S.BTN_FECHAR_MODAL):
                await self.page.click(S.BTN_FECHAR_MODAL, timeout=3)
        except Exception:
            pass
        return chegou()

    async def _procurar_no_mapa(self, slug: str, marcador: str):
        """Abre a região do Mapa onde a área está. Primeiro a que o jogo diz (`area` da hunt); se
        o marcador não estiver lá (ex.: Pupitar vem com area "kanto" mas mora no mapa de Johto),
        as outras regiões liberadas, uma a uma — os mesmos botões que o jogador clica."""
        tentadas = []
        preferida = self.hunt_regiao.get(slug)
        regioes = await self.page.evaluate(S.JS_REGIOES_DO_MAPA) or []
        ordem = ([preferida] if preferida in regioes else []) + [r for r in regioes if r != preferida]
        for r in ordem:
            await self.page.click_presente(S.MAPA_REGIAO.format(regiao=r), timeout=5)
            tentadas.append(r)
            fim = time.monotonic() + 2.5
            while time.monotonic() < fim:
                if await self.page.exists(marcador):
                    if r != preferida:
                        self.hunt_regiao[slug] = r          # lembra para a próxima vez
                    return
                await asyncio.sleep(0.25)

    async def _wait_for(self, cond, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            await self.wait_change(min(1.0, max(0.05, end - time.monotonic())))
        return cond()
