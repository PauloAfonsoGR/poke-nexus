"""As páginas do PokeIdle embutidas na janela do programa (Qt WebEngine).

Cada conta tem um QWebEngineProfile persistente próprio (profiles/conta_XX/web):
cookies, LocalStorage e login nunca se misturam. As páginas vivem aqui, na thread
da interface; os workers (na thread do asyncio) pedem para abrir/fechar por meio
de sinais e conversam com a página pelo DevTools (ver browser/cdp.py).
"""
import concurrent.futures
import os
import socket

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import (QWebEngineGlobalSettings, QWebEnginePage, QWebEngineProfile,
                                     QWebEngineProfileBuilder)
from shiboken6 import isValid
from PySide6.QtWebEngineWidgets import QWebEngineView

# Só desempenho: páginas escondidas (contas não selecionadas) continuam rodando normalmente.
# Testados e NÃO adotados na versão normal: --disable-gpu (bem menos RAM, mas muda o desenho das
# imagens — é o Modo Leve), congelar páginas escondidas (pararia o WebSocket e o farm das contas
# fora da tela) e --force-gpu-mem-available-mb=256: no jogo 1.279 ele economizava ~27%, mas no 1.287
# a página VISÍVEL incha muito mais rápido com ele (medido: 1.991 MB com o teto × 604 MB sem).
CHROMIUM_FLAGS = ("--disable-background-timer-throttling --disable-renderer-backgrounding "
                  "--disable-backgrounding-occluded-windows "
                  "--disable-features=IntensiveWakeUpThrottling")
# Modo Leve 2.0 (medido em docs/desempenho): "reduzir movimento", que o CSS do PokeIdle respeita
# (desliga as animações de enfeite). O Leve antigo também forçava --disable-gpu, e num PC com placa de
# vídeo isso deixava o jogo MAIS travado (uma conta: 38,8 × 60 quadros/s, tecla→tela 112 × 48 ms, e
# mais CPU). Agora a placa só fica de fora quando o PC não tem uma; aí o Chromium desenha por software e
# o Qt também (QT_QUICK_BACKEND=software), em vez de emular a placa pela CPU (WARP): metade da CPU
# com mais quadros. O farm, o WebSocket e os timers do jogo não mudam.
CHROMIUM_FLAGS_LEVE_EXTRA = "--force-prefers-reduced-motion"
# Como o Leve desenha nesta máquina (preenchido por setup_environment): "gpu", "software" ou "" (normal).
DESENHO_LEVE = ""
# DNS seguro (DNS por HTTPS) com volta para o DNS do Windows. Um amigo do usuário via
# "ERR_NAME_NOT_RESOLVED" só no PokeNexus: o DNS do PC dele não achava o pokeidle.io. Com o modo
# "SecureWithFallback" o Chromium pergunta a estes servidores e, se não der, usa o do Windows como
# sempre: para quem o DNS já funciona nada muda. Vale para todos os perfis (4 contas e a página de
# dados do Hunt). Ver docs/rede/RELATORIO.md.
DNS_SERVIDORES = ["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"]
DNS_SEGURO = False      # setup_environment conseguiu ligar?


def configurar_dns() -> bool:
    """Liga o DNS seguro com volta. Precisa rodar antes de criar qualquer perfil ou página."""
    try:
        modo = QWebEngineGlobalSettings.DnsMode()
        modo.secureMode = QWebEngineGlobalSettings.SecureDnsMode.SecureWithFallback
        modo.serverTemplates = DNS_SERVIDORES
        return bool(QWebEngineGlobalSettings.setDnsMode(modo))
    except Exception:
        return False        # sem a função (Qt antigo): fica o DNS do Windows, como antes


def tem_gpu() -> bool:
    """Há uma placa de vídeo de verdade (DXGI)? Fica de fora o adaptador de software do Windows
    ("Microsoft Basic Render Driver", o que aparece sem driver de vídeo). Na dúvida, True: o próprio
    Chromium cai para o software se a placa não servir."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        class Desc(ctypes.Structure):
            _fields_ = [("Description", wintypes.WCHAR * 128), ("VendorId", wintypes.UINT),
                        ("DeviceId", wintypes.UINT), ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT),
                        ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                        ("SharedSystemMemory", ctypes.c_size_t), ("LuidLow", wintypes.DWORD),
                        ("LuidHigh", wintypes.LONG), ("Flags", wintypes.UINT)]

        class Guid(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        def metodo(obj, indice, *tipos):
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *tipos)(vtbl[indice])

        iid = Guid(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
        fabrica = ctypes.c_void_p()
        if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(fabrica)) != 0:
            return True
        try:
            i = 0
            while True:
                adaptador = ctypes.c_void_p()
                # IDXGIFactory1::EnumAdapters1 (12); IDXGIAdapter1::GetDesc1 (10); Release (2)
                if metodo(fabrica, 12, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(
                        fabrica, i, ctypes.byref(adaptador)) != 0:
                    return False          # acabou a lista sem achar placa de verdade
                d = Desc()
                ok = metodo(adaptador, 10, ctypes.POINTER(Desc))(adaptador, ctypes.byref(d)) == 0
                metodo(adaptador, 2)(adaptador)
                if ok and not d.Flags & 2 and not (d.VendorId == 0x1414 and d.DeviceId == 0x8C):
                    return True
                i += 1
        finally:
            metodo(fabrica, 2)(fabrica)
    except Exception:
        return True


def setup_environment() -> int:
    """Precisa rodar ANTES de criar o QApplication. Devolve a porta do DevTools.

    O DevTools só escuta em 127.0.0.1 (nada de fora do computador acessa) e numa porta
    livre sorteada a cada execução.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{port}"
    global DESENHO_LEVE
    from app.config import MODO_LEVE
    flags = CHROMIUM_FLAGS
    if MODO_LEVE:
        flags += " " + CHROMIUM_FLAGS_LEVE_EXTRA
        if tem_gpu():
            DESENHO_LEVE = "gpu"
        else:
            DESENHO_LEVE = "software"
            flags += " --disable-gpu"
            os.environ["QT_QUICK_BACKEND"] = "software"     # antes do QApplication
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + flags).strip()
    global DNS_SEGURO
    DNS_SEGURO = configurar_dns()
    return port


class GamePage(QWebEnginePage):
    """Página do jogo: sem poluir o console, e links externos abrem no navegador padrão."""

    def javaScriptConsoleMessage(self, *_):
        pass

    def createWindow(self, _type):
        tmp = QWebEnginePage(self.profile(), self)

        def abrir_fora(url: QUrl):
            if url.isValid() and not url.isEmpty():
                QDesktopServices.openUrl(url)
            tmp.deleteLater()
        tmp.urlChanged.connect(abrir_fora)
        return tmp


class WebHost(QObject):
    view_added = Signal(int, object)     # índice da conta, QWebEngineView
    view_removed = Signal(int)
    _open_sig = Signal(int, str, str, float, object)
    _close_sig = Signal(int, object)
    _data_sig = Signal(str, object)
    _data_close_sig = Signal(object)

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self._profiles: dict[int, QWebEngineProfile] = {}
        self._items: dict[int, tuple[GamePage, QWebEngineView]] = {}
        # Processo de renderização de cada conta (lido de qualquer thread pela vigia de memória).
        self.pids: dict[int, int] = {}
        self._data_profile: QWebEngineProfile | None = None
        self._data_page: QWebEnginePage | None = None
        self._open_sig.connect(self._do_open, Qt.QueuedConnection)
        self._close_sig.connect(self._do_close, Qt.QueuedConnection)
        self._data_sig.connect(self._do_open_data, Qt.QueuedConnection)
        self._data_close_sig.connect(self._do_close_data, Qt.QueuedConnection)
        # O aviso `renderProcessPidChanged` não chega em toda versão do Qt: o PID é lido da própria
        # página a cada 5 s (na thread da tela; a vigia só lê o dicionário).
        self._pid_timer = QTimer(self)
        self._pid_timer.timeout.connect(self._ler_pids)
        self._pid_timer.start(5000)

    def _ler_pids(self):
        for i, (page, _view) in list(self._items.items()):
            try:
                pid = page.renderProcessPid()
            except RuntimeError:
                continue
            if pid:
                self.pids[i] = pid

    # -------------------------------------------- chamadas de qualquer thread
    def open(self, index: int, storage_dir: str, marker_url: str, zoom: float) -> concurrent.futures.Future:
        fut = concurrent.futures.Future()
        self._open_sig.emit(index, storage_dir, marker_url, zoom, fut)
        return fut

    def close(self, index: int) -> concurrent.futures.Future:
        fut = concurrent.futures.Future()
        self._close_sig.emit(index, fut)
        return fut

    def open_data_page(self, marker_url: str) -> concurrent.futures.Future:
        """Página de DADOS do Hunt Analyzer: sem janela, sem login (perfil anônimo, nada é
        gravado), separada de todas as contas. Só lê os arquivos públicos do jogo."""
        fut = concurrent.futures.Future()
        self._data_sig.emit(marker_url, fut)
        return fut

    def close_data_page(self) -> concurrent.futures.Future:
        fut = concurrent.futures.Future()
        self._data_close_sig.emit(fut)
        return fut

    def _do_close_data(self, fut):
        if self._data_page is not None:
            self._delete_later(self._data_page)
            self._data_page = None
        fut.set_result(True)

    def _do_open_data(self, marker_url, fut):
        try:
            if self._data_page is not None:
                self._delete_later(self._data_page)
            if self._data_profile is None:
                self._data_profile = QWebEngineProfile(self)      # sem nome = anônimo, em memória
            self._data_page = GamePage(self._data_profile, self)
            self._data_page.load(QUrl(marker_url))
            fut.set_result(True)
        except Exception as e:
            fut.set_exception(e)

    # --------------------------------------------------- thread da interface
    def view(self, index: int) -> QWebEngineView | None:
        item = self._items.get(index)
        return item[1] if item else None

    def _profile(self, index: int, storage_dir: str) -> QWebEngineProfile:
        # O perfil vive enquanto o programa estiver aberto: reiniciar a conta só troca a página.
        if index not in self._profiles:
            b = QWebEngineProfileBuilder()
            b.setPersistentStoragePath(storage_dir)
            b.setCachePath(os.path.join(storage_dir, "cache"))
            b.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
            perfil = b.createProfile(f"pokeidle_{index + 1}")
            # Cache em disco com teto (o jogo usa ~35 MB; sem teto o Chromium deixa crescer).
            perfil.setHttpCacheMaximumSize(64 * 1024 * 1024)
            self._profiles[index] = perfil
        return self._profiles[index]

    def _do_open(self, index, storage_dir, marker_url, zoom, fut):
        try:
            self._do_close(index, None)
            os.makedirs(storage_dir, exist_ok=True)
            page = GamePage(self._profile(index, storage_dir), self)
            page.renderProcessPidChanged.connect(lambda pid, i=index: self.pids.__setitem__(i, pid))
            view = QWebEngineView()
            view.setPage(page)
            view.setZoomFactor(zoom)
            page.load(QUrl(marker_url))
            self._items[index] = (page, view)
            self.view_added.emit(index, view)
            fut.set_result(True)
        except Exception as e:
            fut.set_exception(e)

    def _do_close(self, index, fut):
        item = self._items.pop(index, None)
        self.pids.pop(index, None)
        if item:
            page, view = item
            self.view_removed.emit(index)
            try:
                if isValid(view):
                    view.setParent(None)
            except RuntimeError:
                pass
            self._delete_later(view)
            self._delete_later(page)
        if fut:
            fut.set_result(True)

    def close_all(self):
        """Fecha todas as páginas e perfis (ao sair do programa)."""
        for i in list(self._items):
            self._do_close(i, None)
        if self._data_page is not None:
            self._delete_later(self._data_page)
            self._data_page = None
        for p in [*self._profiles.values(), *([self._data_profile] if self._data_profile else [])]:
            self._delete_later(p)
        self._profiles.clear()
        self._data_profile = None

    @staticmethod
    def _delete_later(obj):
        """Qt pode já ter destruído o wrapper C++ durante o fechamento do WebEngine."""
        try:
            if obj is not None and isValid(obj):
                obj.deleteLater()
        except RuntimeError:
            pass
