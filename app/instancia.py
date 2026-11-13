"""Uma cópia só do PokeNexus por pasta de dados.

Duas cópias abertas usam os mesmos perfis e as mesmas contas, e o jogo derruba a sessão. Com o X deixando o
programa na bandeja, é fácil esquecer e clicar no atalho de novo. Então, ao abrir (main.py, antes de criar
página, perfil ou conta):

- um mutex do Windows com nome fixo (por usuário e por pasta de dados) diz se há outra cópia VIVA. O Windows
  apaga o mutex quando o processo termina, mesmo num travamento ou "Finalizar tarefa": uma cópia que morreu
  nunca impede de abrir (não sobra nome preso);
- se há outra, esta pede a ela (QLocalSocket, mesmo nome) para mostrar a janela e fecha na hora;
- se a outra está saindo (Sair, atualizador), espera ela terminar e abre;
- se a outra está viva mas não responde (travada), pergunta se pode fechar a travada e abrir esta.

POKENEXUS_DATA diferente = nome diferente = cópias independentes (é assim que os testes rodam).
"""
import ctypes
import hashlib
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ERROR_ALREADY_EXISTS = 183
ASFW_ANY = 0xFFFFFFFF
# A outra cópia pode estar abrindo (a janela leva alguns segundos para nascer) ou terminando de parar as contas.
ESPERA_RESPOSTA_S = 15
ESPERA_SAINDO_S = 90

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
k32.CreateMutexW.restype = wintypes.HANDLE
k32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD))
k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
user32.AllowSetForegroundWindow.argtypes = (wintypes.DWORD,)


class Instancia(QObject):
    mostrar = Signal()          # outra cópia pediu: mostre a janela (main.py liga em MainWindow.restaurar)

    def __init__(self, pasta_dados: Path):
        super().__init__()
        chave = f"{os.environ.get('USERNAME', '')}|{os.path.normcase(os.path.abspath(pasta_dados))}"
        self.nome = "PokeNexus-" + hashlib.sha256(chave.encode("utf-8")).hexdigest()[:24]
        self.arq_pid = Path(pasta_dados) / "instancia.pid"
        self.saindo = lambda: False          # main.py: a janela já está fechando de verdade?
        self._mutex = None
        self._servidor = None

    # ---------------------------------------------------------------- ao abrir
    def abrir(self) -> bool:
        """True: esta é a única cópia, pode seguir. False: a outra cópia mostrou a janela (ou a pessoa
        desistiu): feche esta sem criar nada."""
        if self._pegar_mutex():
            return True
        fim = time.monotonic() + ESPERA_RESPOSTA_S
        esperou_saida = False
        while True:
            r = self._pedir(max(0.5, fim - time.monotonic()))
            if r == "ok":
                return False
            if r == "saindo" and not esperou_saida:
                esperou_saida = True
                fim = time.monotonic() + ESPERA_SAINDO_S
            if self._pegar_mutex():        # a outra terminou
                return True
            if time.monotonic() >= fim:
                break
            time.sleep(.25)
        return self._travada()

    def _pegar_mutex(self) -> bool:
        h = k32.CreateMutexW(None, False, "Local\\" + self.nome)
        erro = ctypes.get_last_error()
        if not h:
            return True                     # sem mutex (erro do Windows): não impede de abrir
        if erro == ERROR_ALREADY_EXISTS:
            k32.CloseHandle(h)
            return False
        self._mutex = h                     # fica aberto até o processo terminar
        try:
            self.arq_pid.parent.mkdir(parents=True, exist_ok=True)
            self.arq_pid.write_text(str(os.getpid()), encoding="ascii")
        except OSError:
            pass
        self._escutar()
        return True

    def _pedir(self, espera_s: float) -> str | None:
        """Pede para a outra cópia mostrar a janela. Devolve a resposta ("ok" ou "saindo") ou None."""
        s = QLocalSocket()
        s.connectToServer(self.nome)
        if not s.waitForConnected(1000):
            return None
        # Deixa a outra cópia vir para a frente (o Windows só deixa quem o usuário acabou de abrir).
        user32.AllowSetForegroundWindow(ASFW_ANY)
        s.write(b"mostrar\n")
        s.waitForBytesWritten(1000)
        fim = time.monotonic() + espera_s
        while not s.canReadLine() and time.monotonic() < fim:
            if not s.waitForReadyRead(int(max(50, (fim - time.monotonic()) * 1000))):
                break
        r = bytes(s.readLine()).decode("ascii", "replace").strip() if s.canReadLine() else None
        s.abort()
        return r

    def _travada(self) -> bool:
        from app.dialogos import avisar, perguntar
        pid = self._pid_da_outra()
        if pid is None:
            avisar(None, "PokeNexus", "Já existe um PokeNexus aberto, mas ele não respondeu.\n\n"
                                      "Feche ele no Gerenciador de Tarefas e abra de novo.", "aviso")
            return False
        if not perguntar(None, "PokeNexus", "Já existe um PokeNexus aberto, mas ele não responde.\n\n"
                                            "Fechar o que está travado e abrir de novo? As contas dele param.",
                         sim="Fechar e abrir", nao="Cancelar", perigo=True):
            return False
        h = k32.OpenProcess(0x0001 | 0x00100000, False, pid)        # TERMINATE | SYNCHRONIZE
        if h:
            try:
                k32.TerminateProcess(h, 1)
                k32.WaitForSingleObject(h, 15000)
            finally:
                k32.CloseHandle(h)
        fim = time.monotonic() + 15
        while time.monotonic() < fim:
            if self._pegar_mutex():
                return True
            time.sleep(.25)
        avisar(None, "PokeNexus", "Não consegui fechar o PokeNexus travado.\n\n"
                                  "Feche ele no Gerenciador de Tarefas e abra de novo.", "erro")
        return False

    def _pid_da_outra(self) -> int | None:
        """O PID gravado pela outra cópia, só se ainda for este mesmo programa (PokeNexus.exe; python.exe
        rodando do código)."""
        try:
            pid = int(self.arq_pid.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
        if pid == os.getpid():
            return None
        h = k32.OpenProcess(0x1000, False, pid)                     # QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            n = wintypes.DWORD(len(buf))
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return None
        finally:
            k32.CloseHandle(h)
        nome = os.path.normcase(os.path.basename(buf.value))
        return pid if nome == os.path.normcase(os.path.basename(sys.executable)) else None

    # ---------------------------------------------------------- já aberta
    def _escutar(self):
        srv = QLocalServer(self)
        srv.setSocketOptions(QLocalServer.UserAccessOption)          # só o mesmo usuário do Windows
        if not srv.listen(self.nome):
            QLocalServer.removeServer(self.nome)
            if not srv.listen(self.nome):
                return                      # sem servidor o mutex continua impedindo a segunda cópia
        srv.newConnection.connect(self._conexao)
        self._servidor = srv

    def _conexao(self):
        while self._servidor.hasPendingConnections():
            s = self._servidor.nextPendingConnection()
            s.readyRead.connect(lambda s=s: self._ler(s))
            s.disconnected.connect(s.deleteLater)
            if s.canReadLine():
                self._ler(s)

    def _ler(self, s: QLocalSocket):
        while s.canReadLine():
            if bytes(s.readLine()).strip() != b"mostrar":
                continue
            saindo = self.saindo()
            s.write(b"saindo\n" if saindo else b"ok\n")
            s.flush()
            if not saindo:
                self.mostrar.emit()
