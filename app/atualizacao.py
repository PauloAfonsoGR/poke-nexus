"""Aviso de atualização: procura uma versão nova nas Releases do GitHub e, com o clique da pessoa, baixa
e instala.

- Só no programa instalado (empacotado pelo GitHub Actions, com `app/_build.py`). Rodando do código, ou
  num build local sem número de versão, fica desligado.
- Procura 30 s depois de abrir e depois a cada 6 h, numa thread à parte (não trava a janela nem o loop
  das contas). Sem internet, GitHub fora ou resposta estranha: só uma linha no log, nada na tela.
- Repositório público: a consulta é anônima. NUNCA ponha token aqui.
- Nada acontece sozinho: o download e a instalação só começam no botão "Atualizar".
- O instalador (Inno Setup) é baixado só de endereços do GitHub, conferido pelo SHA256SUMS.txt da mesma
  Release e rodado depois que o PokeNexus fecha pelo mesmo caminho do X (as contas param com segurança).
  Os dados (%LOCALAPPDATA%\\PokeNexus) não são tocados.
"""
import base64
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout)

from app import config_edit
from app.config import APP_NAME, APP_VERSION, CONFIG_PATH, VERSAO_DE_BUILD
from app.dialogos import avisar, perguntar
from app.icones import TAM as ICO_TAM, icone
from app.molduras import Botao, Moldura
from app.tema import carregar_fontes, qss_dialogo

URL_RELEASES = "https://api.github.com/repos/PauloAfonsoGR/poke-nexus/releases/latest"
# Só para testes: um servidor local falso de Releases (ver docs/atualizacao/RELATORIO.md).
URL_TESTE = os.environ.get("POKENEXUS_ATUALIZACAO_URL", "").strip()
# De onde o instalador pode ser baixado (o github.com redireciona para os servidores de arquivos dele).
HOSTS_GITHUB = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
# Se o DNS do Windows não achar o GitHub: a mesma pergunta ao DNS seguro, pelo IP (ver _abrir). Primeiro a
# Cloudflare; o Google fica de segunda porque o certificado dele vem de outra raiz (o Python só confia nas raízes
# que o Windows já tem, e o Windows só baixa uma raiz quando algum programa dele precisa: medido em 22/10/2026).
URLS_DOH = ("https://1.1.1.1/dns-query", "https://8.8.8.8/resolve")
PRIMEIRA_S = 30
INTERVALO_S = 6 * 3600
TIMEOUT_S = 10
ARGS_INSTALADOR = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


# ------------------------------------------------------------------ sem tela (testável sozinho)
def versao_tupla(v: str) -> tuple[int, int, int] | None:
    """'1.1.57' ou 'v1.1.57' -> (1, 1, 57). Comparado como números: 1.1.57 < 1.1.102 < 1.2.1."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def ligado() -> bool:
    """A checagem só existe no programa empacotado e com número de versão de verdade."""
    return bool(getattr(sys, "frozen", False)) and VERSAO_DE_BUILD and versao_tupla(APP_VERSION) is not None


def endereco_permitido(url: str) -> bool:
    p = urlparse(url)
    if URL_TESTE and p.hostname in ("127.0.0.1", "localhost"):
        return p.scheme in ("http", "https")            # servidor falso dos testes
    return p.scheme == "https" and (p.hostname or "").lower() in HOSTS_GITHUB


class ErroAtualizacao(Exception):
    pass


def resolver_doh(host: str, timeout: float = TIMEOUT_S) -> list[str]:
    """Os IPv4 de `host` pelo DNS seguro, chamado pelo IP (não depende do DNS do Windows)."""
    erro = None
    for base in URLS_DOH:
        req = urllib.request.Request(f"{base}?name={quote(host)}&type=A", headers={
            "Accept": "application/dns-json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = json.loads(r.read(100_000).decode("utf-8"))
        except (OSError, ValueError) as e:          # URLError é OSError
            erro = e
            continue
        ips = [a["data"] for a in dados.get("Answer") or [] if a.get("type") == 1 and a.get("data")]
        if ips:
            return ips
        erro = OSError(f"o DNS seguro não achou {host}")
    raise erro if isinstance(erro, OSError) else OSError(f"DNS seguro sem resposta ({erro})")


class _ConexaoDoh(http.client.HTTPSConnection):
    """HTTPS para o IP achado por resolver_doh; o certificado continua conferido pelo nome do host."""

    def connect(self):
        sock = socket.create_connection((resolver_doh(self.host, self.timeout)[0], self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _HttpsDoh(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ConexaoDoh, req, context=self._context)


def _abrir(url: str, cabecalhos: dict | None = None, timeout: float = TIMEOUT_S):
    def pedido():
        return urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", **(cabecalhos or {})})
    try:
        return urllib.request.urlopen(pedido(), timeout=timeout)
    except urllib.error.URLError as e:
        # O DNS do Windows não achou o GitHub (o mesmo defeito do ERR_NAME_NOT_RESOLVED no jogo): tenta de novo
        # perguntando o endereço ao DNS seguro. Qualquer outro erro segue igual.
        if not isinstance(e.reason, socket.gaierror) or urlparse(url).scheme != "https":
            raise
    return urllib.request.build_opener(_HttpsDoh()).open(pedido(), timeout=timeout)


def ler_release(dados: dict) -> dict:
    """A resposta da API de Releases -> o que o aviso precisa (ou ErroAtualizacao)."""
    versao = str(dados.get("tag_name") or "").lstrip("v")
    if versao_tupla(versao) is None:
        raise ErroAtualizacao(f"versão estranha na Release: {dados.get('tag_name')!r}")
    setup = sums = None
    for a in dados.get("assets") or []:
        nome, url = str(a.get("name") or ""), str(a.get("browser_download_url") or "")
        if re.fullmatch(r"PokeNexus-Setup-[\w.\-]+\.exe", nome):
            setup = (nome, url)
        elif nome == "SHA256SUMS.txt":
            sums = url
    if not setup or not sums:
        raise ErroAtualizacao("a Release não tem o instalador e o SHA256SUMS.txt")
    if not endereco_permitido(setup[1]) or not endereco_permitido(sums):
        raise ErroAtualizacao(f"endereço de download fora do GitHub: {setup[1]}")
    linhas = [l.strip(" -*\t") for l in str(dados.get("body") or "").splitlines()]
    return {"versao": versao, "setup_nome": setup[0], "setup_url": setup[1], "sums_url": sums,
            "resumo": [l for l in linhas if l][:5], "pagina": str(dados.get("html_url") or "")}


class Consulta:
    """GET da Release mais nova, com ETag (resposta 304 = nada mudou, não gasta o limite da API)."""

    def __init__(self, url: str):
        self.url = url
        self.etag = ""
        self.ultima: dict | None = None

    def buscar(self) -> dict:
        cab = {"Accept": "application/vnd.github+json"}
        if self.etag and self.ultima:
            cab["If-None-Match"] = self.etag
        try:
            with _abrir(self.url, cab) as r:
                corpo = r.read(2_000_000)
                etag = r.headers.get("ETag", "")
        except urllib.error.HTTPError as e:
            if e.code == 304 and self.ultima:
                return self.ultima
            raise ErroAtualizacao(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ErroAtualizacao(f"sem conexão ({getattr(e, 'reason', e)})") from None
        try:
            info = ler_release(json.loads(corpo.decode("utf-8")))
        except (ValueError, AttributeError, TypeError) as e:
            raise ErroAtualizacao(f"resposta inválida ({e})") from None
        self.etag, self.ultima = etag, info
        return info


def sha256_esperado(texto: str, nome: str) -> str | None:
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) == 2 and partes[1].lstrip("*") == nome and re.fullmatch(r"[0-9a-fA-F]{64}", partes[0]):
            return partes[0].lower()
    return None


def baixar(url: str, destino: Path, progresso=None, cancelado: threading.Event | None = None) -> None:
    """Baixa em pedaços; confere o endereço antes e depois dos redirecionamentos."""
    if not endereco_permitido(url):
        raise ErroAtualizacao(f"endereço de download fora do GitHub: {url}")
    with _abrir(url, timeout=30) as r:
        if not endereco_permitido(r.geturl()):
            raise ErroAtualizacao(f"o download foi redirecionado para fora do GitHub: {urlparse(r.geturl()).hostname}")
        total = int(r.headers.get("Content-Length") or 0)
        feito = 0
        with open(destino, "wb") as f:
            while True:
                if cancelado is not None and cancelado.is_set():
                    raise ErroAtualizacao("cancelado")
                bloco = r.read(256 * 1024)
                if not bloco:
                    break
                f.write(bloco)
                feito += len(bloco)
                if progresso:
                    progresso(feito, total)


def _apagar(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass                               # ainda aberto pela thread do download: fica no temp


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def instalar_quando_fechar(setup: Path, pid: int) -> int:
    """Deixa um PowerShell escondido (o "ajudante") esperando ESTE processo terminar e então roda o
    instalador em modo silencioso (ele reabre o PokeNexus). Assim o instalador nunca encontra o programa
    ainda fechando. Devolve o PID do ajudante. Logs em %TEMP%: PokeNexus-atualizacao-ajudante.log (o
    ajudante) e PokeNexus-atualizacao.log (o instalador)."""
    tmp = Path(tempfile.gettempdir())
    aspas = lambda s: "'" + str(s).replace("'", "''") + "'"
    args = ", ".join(aspas(a) for a in ARGS_INSTALADOR + [f'/LOG="{tmp / "PokeNexus-atualizacao.log"}"'])
    registro = aspas(tmp / "PokeNexus-atualizacao-ajudante.log")
    script = (f"$r = {registro}; Add-Content $r \"$(Get-Date -Format s) esperando o PokeNexus (PID {pid}) fechar\"; "
              f"Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue; "
              f"try {{ $p = Start-Process -FilePath {aspas(setup)} -ArgumentList {args} -PassThru; "
              f"Add-Content $r \"$(Get-Date -Format s) instalador iniciado (PID $($p.Id))\" }} "
              f"catch {{ Add-Content $r \"$(Get-Date -Format s) ERRO ao iniciar o instalador: $_\" }}")
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand",
           base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
    # Console escondido (CREATE_NO_WINDOW) e grupo próprio. NÃO usar DETACHED_PROCESS: sem console
    # nenhum o PowerShell 5.1 sai sem rodar o script (medido: o instalador nunca começava).
    base = 0x08000000 | 0x00000200
    # Fora de um "job" do Windows (alguns lançadores abrem o programa dentro de um): se o job fechar
    # junto com o PokeNexus, o ajudante não pode morrer com ele. Se o job não deixar sair, vai sem.
    for flags in (base | 0x01000000, base):          # CREATE_BREAKAWAY_FROM_JOB
        try:
            return subprocess.Popen(cmd, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid
        except OSError:
            continue
    raise ErroAtualizacao("não consegui iniciar o ajudante da instalação")


# ------------------------------------------------------------------ o relógio (na thread da tela)
class Atualizador(QObject):
    """Procura em segundo plano e avisa a janela pelo sinal `nova` (sempre entregue na thread da tela)."""
    nova = Signal(dict)
    _manual = Signal(str, object)          # resposta do "Procurar atualização agora"

    def __init__(self, cfg: dict, log, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.log = log                     # log(msg): "Sistema - atualização: ..."
        self.consulta = Consulta(URL_TESTE or URL_RELEASES)
        self._rodando = False
        self._resposta_manual = None
        self._manual.connect(self._entregar_manual)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.procurar)
        if ligado():
            QTimer.singleShot(PRIMEIRA_S * 1000, self.procurar)
            self.timer.start(INTERVALO_S * 1000)

    def _opcoes(self) -> dict:
        return self.cfg.setdefault("atualizacao", {"avisar": True, "versao_pulada": ""})

    def procurar(self, manual: bool = False, resposta=None):
        """Automático: respeita "Avisar quando tiver atualização". Manual (Ajustes): sempre procura e
        chama resposta(estado, info) com estado = nova | atual | erro | desligado."""
        if not ligado():
            if manual and resposta:
                resposta("desligado", None)
            return
        if not manual and not self._opcoes().get("avisar", True):
            return
        if self._rodando:
            return
        self._rodando = True
        self._resposta_manual = resposta if manual else None
        threading.Thread(target=self._checar, args=(manual,), daemon=True, name="atualizacao").start()

    def _checar(self, manual: bool):
        try:
            info = self.consulta.buscar()
        except Exception as e:                           # nada na tela: só o log
            self.log(f"atualização: não consegui procurar versão nova ({e})")
            self._rodando = False
            if manual:
                self._manual.emit("erro", str(e))
            return
        self._rodando = False
        nova, atual = versao_tupla(info["versao"]), versao_tupla(APP_VERSION)
        if nova <= atual:
            self.log(f"atualização: em dia (instalada {APP_VERSION}, no GitHub {info['versao']})")
            if manual:
                self._manual.emit("atual", info)
            return
        if not manual and info["versao"] == self._opcoes().get("versao_pulada", ""):
            self.log(f"atualização: {info['versao']} disponível, mas foi pulada")
            return
        self.log(f"atualização: versão nova {info['versao']} disponível (instalada {APP_VERSION})")
        self.nova.emit(info)
        if manual:
            self._manual.emit("nova", info)

    def _entregar_manual(self, estado: str, info):
        r, self._resposta_manual = self._resposta_manual, None
        if r:
            r(estado, info)

    def pular(self, versao: str):
        self._opcoes()["versao_pulada"] = versao
        try:
            config_edit.salvar_um(CONFIG_PATH, "atualizacao", "versao_pulada", versao)
        except (OSError, config_edit.ErroConfig) as e:
            self.log(f"atualização: não consegui gravar a versão pulada ({e})")
        self.log(f"atualização: a versão {versao} foi pulada")


# ------------------------------------------------------------------ o aviso
def _botoes() -> tuple[Botao, Botao, Botao]:
    atualizar = Botao(" Atualizar")
    atualizar.setObjectName("primary")
    atualizar.setIcon(icone("salvar", "escuro"))
    atualizar.setIconSize(ICO_TAM)
    depois = Botao("Depois")
    pular = Botao("Pular esta versão")
    for b in (atualizar, depois, pular):
        b.setCursor(Qt.PointingHandCursor)
    atualizar.setToolTip("Baixa a versão nova, fecha o PokeNexus e instala. Os logins e a configuração ficam")
    depois.setToolTip("Esconde o aviso até a próxima procura (a cada 6 horas)")
    pular.setToolTip("Não avisa mais desta versão; a próxima versão volta a avisar")
    return atualizar, depois, pular


class FaixaAtualizacao(Moldura):
    """A faixa discreta no topo da janela. Some sozinha: não ocupa espaço sem versão nova."""
    atualizar = Signal(dict)
    pular = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.info: dict = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 12, 8)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.titulo = QLabel("")
        self.titulo.setObjectName("cardTitle")
        self.resumo = QLabel("")
        self.resumo.setObjectName("muted")
        self.resumo.setWordWrap(True)
        col.addWidget(self.titulo)
        col.addWidget(self.resumo)
        lay.addLayout(col, 1)
        self.b_atualizar, self.b_depois, self.b_pular = _botoes()
        for b in (self.b_atualizar, self.b_depois, self.b_pular):
            lay.addWidget(b, 0, Qt.AlignVCenter)
        self.b_atualizar.clicked.connect(lambda: self.atualizar.emit(self.info))
        self.b_depois.clicked.connect(self.hide)
        self.b_pular.clicked.connect(lambda: (self.hide(), self.pular.emit(self.info.get("versao", ""))))
        self.hide()

    def mostrar(self, info: dict):
        self.info = info
        self.titulo.setText(f"Nova versão {info['versao']} disponível")
        self.resumo.setText("\n".join(info.get("resumo") or []) or "Melhorias e correções.")
        self.show()


class DialogoDownload(QDialog):
    """Baixa o instalador numa thread, com a barra de progresso e o Cancelar."""
    _progresso = Signal(int, int)
    _fim = Signal(str)                  # "" = ok; senão a mensagem de erro

    def __init__(self, parent, info: dict, destino: Path):
        super().__init__(parent)
        carregar_fontes()
        self.info, self.destino = info, destino
        self.cancelado = threading.Event()
        self.erro: str | None = None
        self.esperado: str | None = None      # SHA-256 do SHA256SUMS.txt
        self.obtido: str | None = None        # SHA-256 do arquivo baixado
        self.erro_sums: str | None = None
        self.setWindowTitle("Atualização do PokeNexus")
        self.setStyleSheet(qss_dialogo())
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        t = QLabel(f"Baixando a versão {info['versao']}")
        t.setObjectName("cardTitle")
        lay.addWidget(t)
        self.barra = QProgressBar()
        self.barra.setRange(0, 0)
        lay.addWidget(self.barra)
        self.texto = QLabel("Conectando ao GitHub")
        self.texto.setObjectName("muted")
        lay.addWidget(self.texto)
        base = QHBoxLayout()
        base.addStretch()
        self.b_cancelar = Botao("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        base.addWidget(self.b_cancelar)
        lay.addLayout(base)
        self._progresso.connect(self._mostrar)
        self._fim.connect(self._terminou)
        threading.Thread(target=self._baixar, daemon=True, name="atualizacao-download").start()

    def _baixar(self):
        """Tudo o que usa a rede ou o disco fica nesta thread: o instalador, o SHA256SUMS.txt da mesma
        Release e o SHA-256 do arquivo baixado (a janela e o loop das contas seguem livres)."""
        try:
            baixar(self.info["setup_url"], self.destino, lambda f, t: self._progresso.emit(f, t), self.cancelado)
        except Exception as e:
            self._fim.emit(str(e) or e.__class__.__name__)
            return
        try:
            with _abrir(self.info["sums_url"], timeout=30) as r:
                if not endereco_permitido(r.geturl()):
                    raise ErroAtualizacao("o SHA256SUMS.txt foi redirecionado para fora do GitHub")
                self.esperado = sha256_esperado(r.read(100_000).decode("utf-8", "replace"), self.info["setup_nome"])
            if not self.esperado:
                self.erro_sums = "o instalador não está no SHA256SUMS.txt"
        except Exception as e:
            self.erro_sums = f"não consegui ler o SHA256SUMS.txt ({e})"
        self.obtido = sha256_arquivo(self.destino)
        self._fim.emit("")

    def _mostrar(self, feito: int, total: int):
        if total > 0:
            self.barra.setRange(0, 1000)
            self.barra.setValue(int(feito * 1000 / total))
            self.texto.setText(f"{feito / 1048576:.1f} de {total / 1048576:.1f} MB")
        else:
            self.texto.setText(f"{feito / 1048576:.1f} MB")

    def _cancelar(self):
        self.cancelado.set()
        self.b_cancelar.setEnabled(False)
        self.texto.setText("Cancelando")

    def _terminou(self, erro: str):
        self.erro = erro or None
        self.accept() if not erro else self.reject()

    def closeEvent(self, e):
        self._cancelar()
        super().closeEvent(e)

    def reject(self):
        if self.erro is None and not self.cancelado.is_set():
            self._cancelar()                 # Esc / X: cancela o download antes de fechar
            self.erro = "cancelado"
        super().reject()


# ------------------------------------------------------------------ ligação com a janela principal
class Atualizacao(QObject):
    """O que a MainWindow ganha: o relógio, a faixa e o fluxo do botão Atualizar."""

    def __init__(self, janela, manager, faixa_no_layout):
        super().__init__(janela)
        self.janela, self.m = janela, manager
        self.relogio = Atualizador(manager.cfg, lambda msg: manager._log(None, msg), self)
        self.faixa = FaixaAtualizacao()
        faixa_no_layout(self.faixa)
        self.faixa.atualizar.connect(self.atualizar)
        self.faixa.pular.connect(self.relogio.pular)
        self.relogio.nova.connect(self.faixa.mostrar)

    def procurar_agora(self, parent):
        """Botão do Ajustes. Aqui a pessoa pediu: o resultado aparece (também quando não há nada)."""
        def resposta(estado, info):
            if estado == "nova":
                return                         # a faixa já apareceu
            if estado == "atual":
                avisar(parent, "Atualização", f"Você já tem a versão mais nova ({APP_VERSION}).")
            elif estado == "desligado":
                avisar(parent, "Atualização", "A procura de atualização só funciona no PokeNexus instalado "
                                              f"pelo instalador. Esta é a versão {APP_VERSION}.")
            else:
                avisar(parent, "Atualização", f"Não consegui falar com o GitHub agora.\n\n{info}", "aviso")
        self.relogio.procurar(manual=True, resposta=resposta)

    def atualizar(self, info: dict):
        log = lambda msg: self.m._log(None, msg)
        if self.m.connected_count() and not perguntar(
                self.janela, "Atualizar o PokeNexus", "As contas vão parar para atualizar. Continuar?",
                sim="Atualizar", nao="Cancelar"):
            log("atualização: cancelada (contas conectadas)")
            return
        self.faixa.hide()
        setup = Path(tempfile.mkdtemp(prefix="PokeNexus-atualizacao-")) / info["setup_nome"]
        log(f"atualização: baixando {info['setup_nome']}")
        d = DialogoDownload(self.janela, info, setup)
        d.exec()
        if d.erro:
            _apagar(setup)
            if d.erro == "cancelado":
                log("atualização: download cancelado")
            else:
                log(f"atualização: o download falhou ({d.erro})")
                avisar(self.janela, "Atualização", f"Não consegui baixar a versão nova.\n\n{d.erro}", "aviso")
            self.faixa.mostrar(info)
            return
        if not d.esperado or d.obtido != d.esperado:
            _apagar(setup)
            motivo = d.erro_sums or "o arquivo baixado não confere com o SHA256SUMS.txt"
            log(f"atualização: NÃO instalada, {motivo} (esperado {d.esperado}, baixado {d.obtido})")
            avisar(self.janela, "Atualização", "O arquivo baixado não passou na conferência de segurança e "
                                               "foi apagado. Nada foi instalado.\n\n" + motivo, "erro")
            return
        log(f"atualização: {info['setup_nome']} conferido (SHA-256 ok); fechando para instalar {info['versao']}")
        try:
            ajudante = instalar_quando_fechar(setup, os.getpid())
        except Exception as e:
            log(f"atualização: NÃO instalada ({e})")
            avisar(self.janela, "Atualização", f"Não consegui iniciar a instalação.\n\n{e}", "erro")
            return
        log(f"atualização: instalador agendado (ajudante PID {ajudante}); o PokeNexus reabre na versão nova")
        # O mesmo caminho do X: closeEvent para as contas (manager.shutdown) e fecha as páginas. O
        # ajudante só roda o instalador depois que este processo terminar.
        self.janela.encerrar()
        QApplication.instance().quit()
