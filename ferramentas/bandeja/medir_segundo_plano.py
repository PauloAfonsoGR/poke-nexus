"""Mede o farm com a janela VISÍVEL, MINIMIZADA e ESCONDIDA NA BANDEJA (jogo simulado, sem contas reais).

    .venv\\Scripts\\python.exe ferramentas\\bandeja\\medir_segundo_plano.py --saida <pasta> [--segundos 120]
                                                                           [--extras]

O PokeNexus de verdade (a mesma janela, as mesmas páginas, o mesmo Manager) abre DENTRO deste processo, com
uma pasta de dados temporária. As 4 contas abrem um jogo simulado em 127.0.0.1 (servidor HTTP + WebSocket
daqui) que manda `estado` e `batalha` a cada 0,2 s enquanto a conta caça. Nada do app é mudado em disco.

Em cada fase, por conta: batalhas contadas pelo app, mensagens do WebSocket recebidas pela página, disparos
de um setInterval de 100 ms (o freio de timers do Chromium derruba isso para 1/s), quadros de
requestAnimationFrame, `document.visibilityState`, tempo de um Runtime.evaluate (o farm lê e clica por ele)
e tempo de um clique `element.click()` até a resposta do servidor chegar na página. Do processo: CPU e
memória privada da árvore (PokeNexus + QtWebEngineProcess) e o "Modo de eficiência" do Windows 11 (EcoQoS +
prioridade ociosa) de cada processo.

--extras (com a janela na bandeja): recarrega a página de uma conta e espera o farm voltar sozinho para a
hunt (clique do farm escondido); trava o renderer de uma conta e espera o vigia de travamento reiniciar só
ela; e o vigia de memória com limite baixo. Os tempos dos vigias são encurtados SÓ na memória deste teste.
Depois mostra a janela de novo e confere estado, conta, zoom, layout e se a página aparece desenhada (pixels
da tela, não da memória).
"""
import argparse
import asyncio
import ctypes
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "ferramentas" / "desempenho"))
import sistema as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--saida", required=True)
ap.add_argument("--segundos", type=int, default=120, help="duração de cada fase")
ap.add_argument("--extras", action="store_true")
ap.add_argument("--fases", default="visivel,minimizada,bandeja")
args = ap.parse_args()
saida = Path(args.saida).resolve()
saida.mkdir(parents=True, exist_ok=True)
dados = tempfile.TemporaryDirectory(prefix="dados_", dir=saida)
os.environ["POKENEXUS_DATA"] = dados.name

from websockets.asyncio.server import serve  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

pronto, parar = threading.Event(), threading.Event()
porta_ws = []


async def sessao(ws):
    estado = {"id": id(ws), "nick": "Teste local", "level": 10, "huntSlug": "", "noCentro": False}

    async def enviar(obj):
        await ws.send(json.dumps(obj, separators=(",", ":")))
    await enviar({"t": "welcome", "estado": estado, "hunts": [{"slug": "bosque", "nome": "Bosque de teste"}]})

    async def eventos():
        while True:
            await asyncio.sleep(.2)
            await enviar({"t": "estado", "estado": estado})
            if estado["huntSlug"]:
                await enviar({"t": "batalha", "ev": [{"k": "spawn"},
                             {"k": "morte", "quem": "selvagem", "xpTreinador": 1}]})
    t = asyncio.create_task(eventos())
    try:
        async for msg in ws:
            m = json.loads(msg)
            if m.get("acao") == "hunt":
                estado["huntSlug"] = "bosque"
                await enviar({"t": "estado", "estado": estado})
            elif m.get("acao") == "ping":
                await enviar({"t": "pong", "n": m.get("n")})
    except ConnectionClosed:
        pass
    finally:
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)


def servidor_ws():
    async def rodar():
        async with serve(sessao, "127.0.0.1", 0) as srv:
            porta_ws.append(srv.sockets[0].getsockname()[1])
            pronto.set()
            while not parar.is_set():
                await asyncio.sleep(.05)
    asyncio.run(rodar())


threading.Thread(target=servidor_ws, daemon=True).start()
assert pronto.wait(5), "servidor local não iniciou"
HTML = '''<!doctype html><meta charset="utf-8"><style>.hidden{display:none}
body{font-family:sans-serif;background:#edf3f8;color:#192b42;padding:20px;margin:0;height:100vh}</style>
<div class="hidden"><div id="login">Login escondido pelo pai</div></div>
<div id="app"><h2>Jogo simulado para teste</h2><p>Sem conta real e sem conexão ao PokeIdle.</p>
<button class="marcador" data-slug="bosque" onclick="ws.send(JSON.stringify({acao:'hunt'}))">Caçar</button>
<button id="ping" onclick="ws.send(JSON.stringify({acao:'ping',n:++__m.pings}))">Ping</button>
<p id="estado"></p></div>
<script>
window.__m = {ws:0, tick:0, raf:0, pings:0};
setInterval(()=>__m.tick++, 100);
(function f(){__m.raf++; requestAnimationFrame(f);})();
const ws = new WebSocket('ws://127.0.0.1:PORTA/pokeidle.io');
ws.onmessage=e=>{__m.ws++;const m=JSON.parse(e.data);
  if(m.t==='pong'&&window.__pong){const f=window.__pong;window.__pong=null;f();}
  if(m.estado)document.querySelector('#estado').textContent='Hunt: '+m.estado.huntSlug;};
</script>'''.replace("PORTA", str(porta_ws[0])).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *_):
        pass


http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=http.serve_forever, daemon=True).start()

from browser.web_host import WebHost, setup_environment  # noqa: E402
porta = setup_environment()
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
import app.manager as manager_mod  # noqa: E402
from app.config import load_config, prepare_data_dir  # noqa: E402
from app.gui import MainWindow  # noqa: E402
from app.manager import Manager  # noqa: E402

app = QApplication([])
prepare_data_dir()
cfg, contas = load_config()
cfg["url"] = f"http://127.0.0.1:{http.server_port}/"
cfg["intervalo_inicio_segundos"] = 1
cfg["desempenho"]["economia_em_segundo_plano"] = False   # a página simulada não tem o modo economia
for c in contas:
    c.hunt = "bosque"
web = WebHost(porta)
m = Manager(cfg, contas, web)
m.start()
win = MainWindow(m, web)
win.showMaximized()
resultado = {"segundos_por_fase": args.segundos, "fases": {}, "extras": {}}

# ------------------------------------------------------------------ Windows: modo de eficiência
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class PPTS(ctypes.Structure):
    _fields_ = [("Version", wintypes.DWORD), ("ControlMask", wintypes.DWORD), ("StateMask", wintypes.DWORD)]


k32.GetProcessInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
k32.GetPriorityClass.argtypes = (wintypes.HANDLE,)


def eficiencia(pid: int) -> dict:
    """EcoQoS (ProcessPowerThrottling, EXECUTION_SPEED) e classe de prioridade. O "Modo de eficiência" do
    Gerenciador de Tarefas é os dois juntos: EcoQoS ligado + prioridade ociosa (0x40)."""
    h = k32.OpenProcess(0x0400 | 0x1000, False, pid)
    if not h:
        return {}
    try:
        s = PPTS(1, 0, 0)
        ok = k32.GetProcessInformation(h, 4, ctypes.byref(s), ctypes.sizeof(s))
        prio = k32.GetPriorityClass(h)
        eco = bool(ok and s.ControlMask & 1 and s.StateMask & 1)
        return {"ecoqos": eco, "prioridade": hex(prio), "modo_eficiencia": eco and prio == 0x40}
    finally:
        k32.CloseHandle(h)


def linhas_do_log():
    """As linhas do log em disco (a fila da tela só guarda as últimas 4.000 e enche com as batalhas)."""
    return [l for f in sorted((Path(dados.name) / "logs").glob("*.log"))
            for l in f.read_text(encoding="utf-8", errors="replace").splitlines()]


def viu(trecho):
    return any(trecho in l for l in linhas_do_log()[len(log0):])


log0: list = []


def esperar(cond, timeout=30.0):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        app.processEvents()
        if cond():
            return
        time.sleep(.02)
    win._drain_logs(render=False)
    raise AssertionError("Tempo excedido: " + repr([(w.status, w.detail) for w in m.workers])
                         + "\n" + "\n".join(list(win._log_lines)[-15:]))


def bombear(seg):
    fim = time.monotonic() + seg
    while time.monotonic() < fim:
        app.processEvents()
        time.sleep(.02)


def avaliar(i, js, timeout=15.0):
    f = asyncio.run_coroutine_threadsafe(m.workers[i].page.evaluate(js), m.loop)
    esperar(f.done, timeout)
    return f.result()


def medir_tempo_evaluate(i, n=5):
    tempos = []
    for _ in range(n):
        t = time.perf_counter()
        avaliar(i, "() => 1")
        tempos.append((time.perf_counter() - t) * 1000)
    return statistics.median(tempos)


JS_CLIQUE = ("() => new Promise(r => { const t0 = performance.now();"
             " window.__pong = () => r(performance.now() - t0); document.querySelector('#ping').click(); })")


async def _pedido_marcado(i):
    """Como a compra na liberação (rmt/rotina.py): dorme no loop do Manager até a hora marcada e manda o
    pedido pela página. Devolve o atraso (ms) entre a hora marcada e o pedido sair da página."""
    alvo = time.monotonic() + 0.5
    await asyncio.sleep(alvo - time.monotonic())
    await m.workers[i].page.evaluate("() => { document.querySelector('#ping').click(); return 1; }")
    return (time.monotonic() - alvo) * 1000


def pedido_marcado(i):
    f = asyncio.run_coroutine_threadsafe(_pedido_marcado(i), m.loop)
    esperar(f.done, 10)
    return f.result()


def amostra_processos():
    pids = S.arvore(os.getpid())
    cpu = mem = 0.0
    for p in pids:
        r = S.cpu_e_memoria(p)
        if r:
            cpu += r[0]
            mem += r[1]
    return cpu, mem, pids


def fase(nome):
    print(f"fase {nome}: {args.segundos} s", flush=True)
    bombear(3)
    contadores0 = [avaliar(i, "() => ({...__m})") for i in range(4)]
    batalhas0 = [w.stats.battles for w in m.workers]
    cpu0, _mem, _p = amostra_processos()
    t0 = time.monotonic()
    mems, evals, cliques, marcados, efic = [], [], [], [], {}
    while time.monotonic() - t0 < args.segundos:
        bombear(5)
        _c, mem, pids = amostra_processos()
        mems.append(mem)
        evals.append(medir_tempo_evaluate(time.monotonic_ns() % 4, 1))
        cliques.append(avaliar(int(time.monotonic()) % 4, JS_CLIQUE))
        marcados.append(pedido_marcado(int(time.monotonic()) % 4))
        for p, n in pids.items():
            e = eficiencia(p)
            if e:
                atual = efic.setdefault(f"{n} {p}", e)
                atual["ecoqos"] = atual["ecoqos"] or e["ecoqos"]
                atual["modo_eficiencia"] = atual["modo_eficiencia"] or e["modo_eficiencia"]
    dur = time.monotonic() - t0
    cpu1, _m, _p = amostra_processos()
    contadores1 = [avaliar(i, "() => ({...__m})") for i in range(4)]
    vis = [avaliar(i, "() => document.visibilityState") for i in range(4)]
    por_min = lambda a, b: round((b - a) / dur * 60, 1)  # noqa: E731
    por_s = lambda a, b: round((b - a) / dur, 2)  # noqa: E731
    r = {
        "janela": {"visivel": win.isVisible(), "minimizada": win.isMinimized(),
                   "timer_ms": win.timer.interval()},
        "batalhas_por_min": [por_min(a, w.stats.battles) for a, w in zip(batalhas0, m.workers)],
        "ws_msgs_por_s": [por_s(a["ws"], b["ws"]) for a, b in zip(contadores0, contadores1)],
        "timer_100ms_por_s": [por_s(a["tick"], b["tick"]) for a, b in zip(contadores0, contadores1)],
        "raf_por_s": [por_s(a["raf"], b["raf"]) for a, b in zip(contadores0, contadores1)],
        "visibilityState": vis,
        "evaluate_ms_mediana": round(statistics.median(evals), 1),
        "clique_ate_resposta_ms_mediana": round(statistics.median(cliques), 1),
        "clique_ate_resposta_ms_max": round(max(cliques), 1),
        "pedido_marcado_atraso_ms_mediana": round(statistics.median(marcados), 1),
        "pedido_marcado_atraso_ms_max": round(max(marcados), 1),
        "cpu_pct_maquina": round((cpu1 - cpu0) / (dur * S.NCPU) * 100, 2),
        "memoria_mb_media": round(statistics.mean(mems)),
        "processos_em_modo_eficiencia": sorted(k for k, e in efic.items() if e["modo_eficiencia"]),
        "processos_com_ecoqos": sorted(k for k, e in efic.items() if e["ecoqos"]),
        "prioridades": sorted({e["prioridade"] for e in efic.values()}),
        "n_processos": len(efic),
    }
    resultado["fases"][nome] = r
    print(json.dumps(r, ensure_ascii=False), flush=True)


def fechar_no_x():
    """O X de verdade: WM_CLOSE na janela (o mesmo que o Windows manda no X e no Alt+F4)."""
    user32.PostMessageW(wintypes.HWND(int(win.winId())), 0x0010, 0, 0)


def pixels_da_tela():
    """Cor média da área do jogo na TELA (o que a pessoa vê), não um render em memória."""
    v = win.game.view(win.selected)
    tl = v.mapToGlobal(v.rect().topLeft())
    img = win.screen().grabWindow(0, tl.x(), tl.y(), v.width(), v.height()).toImage()
    pts = [img.pixelColor(img.width() * x // 10, img.height() * y // 10) for x in range(1, 10) for y in range(2, 10)]
    return [round(statistics.mean(getattr(c, k)() for c in pts)) for k in ("red", "green", "blue")]


def estado_tela():
    v = win.game.view(win.selected)
    return {"maximizada": win.isMaximized(), "geometria": list(win.geometry().getRect()),
            "conta": win.selected, "ver_todas": win.grid_mode, "layout_todas": win.game.host.layout_todas,
            "zoom": round(v.zoomFactor(), 3) if v else None, "tam_pagina": [v.width(), v.height()] if v else None}


try:
    esperar(lambda: all(w.game and w.game.hunt_slug == "bosque" and w.stats.battles > 0 for w in m.workers), 60)
    for nome in filter(None, args.fases.split(",")):
        if nome == "visivel":
            win.restaurar() if not win.isVisible() else None
            esperar(lambda: win.isVisible() and not win.isMinimized())
        elif nome == "minimizada":
            cfg["janela"]["minimizar_para_bandeja"] = False      # só na memória: minimizar de verdade
            win.showMinimized()
            esperar(lambda: win.isMinimized())
        elif nome == "bandeja":
            if win.isMinimized():
                win.restaurar()
                esperar(lambda: win.isVisible() and not win.isMinimized())
                bombear(2)
            fechar_no_x()
            esperar(lambda: not win.isVisible())
        fase(nome)

    if args.extras:
        x = resultado["extras"]
        if not win.isVisible() or win.isMinimized():
            win.restaurar()
            esperar(lambda: win.isVisible() and not win.isMinimized())
            bombear(2)
        win.select(1)
        bombear(3)
        antes = estado_tela()
        cel = win.game.cells[1]
        x["diag_antes"] = {"celula": list(cel.geometry().getRect()), "celula_visivel": cel.isVisible(),
                           "view_visivel": win.game.view(1).isVisible(),
                           "view_geo": list(win.game.view(1).geometry().getRect())}

        fechar_no_x()
        esperar(lambda: not win.isVisible())
        # 1) recarregar a página escondida: o farm tem de clicar em "Caçar" de novo sozinho
        t = time.monotonic()
        f = asyncio.run_coroutine_threadsafe(m.workers[3].page.reload(), m.loop)
        esperar(f.done)
        f.result()
        esperar(lambda: m.workers[3].game.welcomed and m.workers[3].game.hunt_slug == "bosque", 60)
        b = m.workers[3].stats.battles
        esperar(lambda: m.workers[3].stats.battles > b + 5, 30)
        x["recarregar_escondida_volta_a_cacar_s"] = round(time.monotonic() - t, 1)
        # 2) vigia de travamento: o renderer da conta 3 trava; só ela é reiniciada
        # O farm conta as batalhas pelos eventos de rede do DevTools, que não passam pelo renderer: o laço da
        # conta só fica preso numa leitura do DOM. Leitura a cada 1 s aqui, para a trava cair numa delas.
        manager_mod.WATCHDOG_SEGUNDOS = 20
        cfg["intervalos"]["verificacao_segundos"] = 1
        log0 = linhas_do_log()
        avaliar(2, "() => { setTimeout(() => { const t = Date.now(); while (Date.now() - t < 90000) {} }, 50);"
                   " return 1; }")
        t = time.monotonic()

        esperar(lambda: viu("worker travado"), 90)
        x["vigia_travamento_disparou_s"] = round(time.monotonic() - t, 1)
        esperar(lambda: m.workers[2].game and m.workers[2].game.welcomed
                and m.workers[2].game.hunt_slug == "bosque" and m.workers[2].status in ("FARMING", "BATALHA"), 90)
        x["vigia_travamento_conta_voltou_s"] = round(time.monotonic() - t, 1)
        manager_mod.WATCHDOG_SEGUNDOS = 150
        # 3) vigia de memória com limite baixo (só na memória do teste)
        manager_mod.MEMORIA_MINUTOS = 0.1
        manager_mod.MEMORIA_INTERVALO_MIN = 60
        cfg["farm"]["limite_memoria_pagina_mb"] = 1
        log0 = linhas_do_log()
        t = time.monotonic()
        esperar(lambda: viu("para liberar memória"), 90)
        cfg["farm"]["limite_memoria_pagina_mb"] = 0
        x["vigia_memoria_disparou_s"] = round(time.monotonic() - t, 1)
        esperar(lambda: all(w.game and w.game.welcomed and w.game.hunt_slug == "bosque" for w in m.workers), 90)
        x["vigia_memoria_contas_cacando"] = True
        x["escondida_durante_extras"] = not win.isVisible()
        # 4) voltar: mesmo estado e a página desenhada na tela
        win.restaurar()
        esperar(lambda: win.isVisible() and not win.isMinimized())
        # Só no teste: por cima de tudo, para a captura da TELA mostrar esta janela (o Windows não deixa um
        # processo de fundo roubar o foco do editor).
        hwnd = wintypes.HWND(int(win.winId()))
        user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        bombear(.3)
        x["pixels_300ms_depois"] = pixels_da_tela()
        r0 = avaliar(win.selected, "() => __m.raf")
        bombear(1)
        x["raf_por_s_depois_de_voltar"] = avaliar(win.selected, "() => __m.raf") - r0
        x["visibilityState_depois_de_voltar"] = avaliar(win.selected, "() => document.visibilityState")
        x["pixels_2s_depois"] = pixels_da_tela()
        g = win.frameGeometry()      # só a área da janela do PokeNexus (nada do resto da tela)
        win.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(str(saida / "voltou_tela.png"))
        user32.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        depois = estado_tela()
        x["tela_antes"], x["tela_depois"] = antes, depois
        x["tela_igual"] = antes == depois
        win.grab().save(str(saida / "voltou.png"))
finally:
    win.sair() if hasattr(win, "sair") else win.encerrar()      # encerrar(): o código de antes da bandeja nova
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    resultado["loop_encerrado"] = not m._thread.is_alive()
    resultado["paginas_fechadas"] = not web._items
    (saida / "resultado.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print("gravado", saida / "resultado.json", flush=True)
    parar.set()
    http.shutdown()
    dados._finalizer.detach()
