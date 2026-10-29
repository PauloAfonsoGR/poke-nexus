"""Teste local com Qt/WebEngine reais e jogo simulado; nenhuma conta do PokeIdle.

python ferramentas/automacao/teste_janela.py --saida <pasta>
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
ap = argparse.ArgumentParser()
ap.add_argument("--saida", required=True)
args = ap.parse_args()
saida = Path(args.saida).resolve()
saida.mkdir(parents=True, exist_ok=True)
dados = tempfile.TemporaryDirectory(prefix="dados_", dir=saida)
os.environ["POKENEXUS_DATA"] = dados.name

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

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
            if json.loads(msg).get("acao") == "hunt":
                estado["huntSlug"] = "bosque"
                await enviar({"t": "estado", "estado": estado})
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
HTML = '''<!doctype html><meta charset="utf-8"><style>.hidden{display:none}body{font-family:sans-serif;background:#edf3f8;color:#192b42;padding:20px}</style>
<div class="hidden"><div id="login">Login escondido pelo pai</div></div>
<div id="app"><h2>Jogo simulado para teste</h2><p>Sem conta real e sem conexão ao PokeIdle.</p>
<button class="marcador" data-slug="bosque" onclick="ws.send(JSON.stringify({acao:'hunt'}))">Caçar</button>
<button id="hunt-eco" onclick="economia(true)">Economia</button>
<button id="eco-sair" onclick="economia(false)">Ligar cena</button><p id="estado"></p></div>
<script>
function economia(on){localStorage.setItem('cfg-economia',on?'1':'0');document.documentElement.classList.toggle('modo-economia',on);}
document.documentElement.classList.toggle('modo-economia',localStorage.getItem('cfg-economia')==='1');
const ws = new WebSocket('ws://127.0.0.1:PORTA/pokeidle.io');
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.estado)document.querySelector('#estado').textContent='Hunt: '+m.estado.huntSlug;};
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

from browser.web_host import WebHost, setup_environment
porta = setup_environment()
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from app.config import prepare_data_dir, load_config
from app.gui import MainWindow
from app.manager import Manager
from app.settings_ui import SettingsDialog

app = QApplication([])
prepare_data_dir()
cfg, contas = load_config()
cfg["url"] = f"http://127.0.0.1:{http.server_port}/"
cfg["intervalo_inicio_segundos"] = 1
cfg["intervalos"]["verificacao_segundos"] = 1
for c in contas:
    c.hunt = "bosque"
web = WebHost(porta)
m = Manager(cfg, contas, web)
m.start()
win = MainWindow(m, web)
win.show()
resumo = {}


def esperar(cond, timeout=30):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        app.processEvents()
        if cond():
            return
        time.sleep(.02)
    raise AssertionError("Tempo excedido: " + repr([(w.status, w.detail) for w in m.workers]))


def avaliar(i, js):
    f = asyncio.run_coroutine_threadsafe(m.workers[i].page.evaluate(js), m.loop)
    esperar(f.done, 10)
    return f.result()


try:
    esperar(lambda: all(w.game and w.game.hunt_slug == "bosque" and w.stats.battles > 0 for w in m.workers))
    resumo["inicio_automatico_e_hunt"] = True
    win.grab().save(str(saida / "janela.png"))
    d = SettingsDialog(win, cfg, contas)
    assert d.w_iniciar.isChecked() and d.w_economia.isChecked()
    assert d.w_bandeja["fechar_para_bandeja"].isChecked()
    d.deleteLater()
    # A preferência já ligada da primeira conta deve continuar ligada após restaurar.
    avaliar(0, "() => economia(true)")
    antes = [w.stats.battles for w in m.workers]
    win.close()
    esperar(lambda: not win.isVisible())
    assert win.bandeja.disponivel and win.bandeja.icone.isVisible()
    esperar(lambda: all(w.stats.battles > n + 5 for w, n in zip(m.workers, antes)), 15)
    esperar(lambda: all(avaliar(i, "() => document.documentElement.classList.contains('modo-economia')")
                        for i in range(4)), 15)
    resumo["bandeja_mantem_batalhas"] = True
    resumo["economia_ativada"] = True
    assert win.timer.interval() == 5000
    # Recarregar na bandeja não perde a preferência que será restaurada.
    f = asyncio.run_coroutine_threadsafe(m.workers[3].page.reload(), m.loop)
    esperar(f.done)
    f.result()
    esperar(lambda: m.workers[3].game.welcomed and m.workers[3].game.hunt_slug == "bosque")
    win.restaurar()
    esperar(lambda: win.isVisible() and not win.isMinimized())
    esperar(lambda: all(not avaliar(i, "() => document.documentElement.classList.contains('modo-economia')")
                        for i in range(1, 4)), 15)
    assert avaliar(0, "() => document.documentElement.classList.contains('modo-economia')")
    resumo["preferencias_restauradas_apos_reload"] = True
    win.showMinimized()
    esperar(lambda: not win.isVisible())
    resumo["minimizar_envia_bandeja"] = True
    win.restaurar()
    m.stop_all()
    esperar(lambda: m.connected_count() == 0)
    resumo["parar_todas"] = True
    m.open_login(0)
    esperar(lambda: m.workers[0].login_open)
    m.stop_all()
    esperar(lambda: not m.workers[0].login_open and not web._items)
    resumo["parar_fecha_login_reserva"] = True
finally:
    win.encerrar()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    resumo["loop_encerrado"] = not m._thread.is_alive()
    resumo["paginas_fechadas"] = not web._items
    (saida / "resultado.json").write_text(json.dumps(resumo, indent=2), encoding="utf-8")
    print(json.dumps(resumo), flush=True)
    parar.set()
    http.shutdown()
    # Chromium pode liberar os perfis só no encerramento do processo.
    dados._finalizer.detach()
