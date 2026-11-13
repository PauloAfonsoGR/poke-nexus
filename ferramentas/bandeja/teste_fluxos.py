"""Fluxos da bandeja e da instância única com o PokeNexus de verdade, em OUTRO processo (como o usuário abre).

    .venv\\Scripts\\python.exe ferramentas\\bandeja\\teste_fluxos.py --saida <pasta> [--exe dist_novo\\PokeNexus\\PokeNexus.exe]

Sem --exe roda `main.py` com o Python do .venv. Cada cópia usa uma pasta de dados temporária NOVA
(POKENEXUS_DATA): as contas abrem na tela de login do PokeIdle e nada das contas reais é tocado.

O teste manda para as janelas as mesmas mensagens que o Windows manda: WM_CLOSE (X), WM_SYSCOMMAND/SC_CLOSE
(Alt+F4), a mensagem do ícone da bandeja (clique, duplo clique, botão direito: o que o Explorer manda para o
Qt), teclas no menu e no aviso, WM_QUERYENDSESSION/WM_ENDSESSION (desligar/sair da conta) e o Restart
Manager do Windows (o que o instalador do Inno Setup usa no CloseApplications). Não move o mouse.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "ferramentas" / "desempenho"))
import sistema as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--saida", required=True)
ap.add_argument("--exe", default="")
args = ap.parse_args()
saida = Path(args.saida).resolve()
saida.mkdir(parents=True, exist_ok=True)

from PySide6.QtGui import QGuiApplication  # noqa: E402

qapp = QGuiApplication([])                 # só para fotografar a tela

user32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
rm = ctypes.WinDLL("rstrtmgr")
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.IsWindowVisible.argtypes = user32.IsZoomed.argtypes = (wintypes.HWND,)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = (wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
ntdll.NtSuspendProcess.argtypes = ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)

WM_CLOSE, WM_SYSCOMMAND, SC_CLOSE = 0x0010, 0x0112, 0xF060
SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE = 0xF020, 0xF030, 0xF120
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.MoveWindow.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL)


def retangulo(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)
WM_QUERYENDSESSION, WM_ENDSESSION, ENDSESSION_CLOSEAPP, ENDSESSION_LOGOFF = 0x0011, 0x0016, 0x1, 0x80000000
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_TAB, VK_SPACE, VK_RETURN, VK_UP, VK_DOWN = 0x09, 0x20, 0x0D, 0x26, 0x28
MYWM_NOTIFYICON = 0x8000 + 101            # WM_APP + 101 (qwindowssystemtrayicon.cpp)
NIN_SELECT, WM_LBUTTONDBLCLK, WM_CONTEXTMENU = 0x0400, 0x0203, 0x007B

resultado: dict = {}
processos_abertos: list[subprocess.Popen] = []


def registrar(nome, ok, detalhe=""):
    resultado[nome] = {"ok": bool(ok), **({"detalhe": detalhe} if detalhe else {})}
    print(f"[{'ok' if ok else 'FALHOU'}] {nome} {detalhe}", flush=True)


def esperar(cond, timeout=30.0, passo=.2):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        r = cond()
        if r:
            return r
        time.sleep(passo)
    return None


def nova_pasta():
    return tempfile.mkdtemp(prefix="pn_bandeja_", dir=saida)


def abrir(dados) -> subprocess.Popen:
    env = dict(os.environ, POKENEXUS_DATA=dados)
    cmd = [args.exe] if args.exe else [str(RAIZ / ".venv" / "Scripts" / "python.exe"), str(RAIZ / "main.py")]
    if args.exe:      # o .exe empacotado: sem o Python do teste no PATH
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if "python" not in p.lower())
    p = subprocess.Popen(cmd, cwd=str(RAIZ), env=env, creationflags=0x08000000,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processos_abertos.append(p)
    return p


def janelas(pids, visiveis_so=False):
    """(hwnd, título, classe, visível) das janelas de nível de topo dos processos `pids`."""
    out = []

    def cb(h, _l):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids:
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, t, 256)
            user32.GetClassNameW(h, c, 256)
            vis = bool(user32.IsWindowVisible(h))
            if vis or not visiveis_so:
                out.append((h, t.value, c.value, vis))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def arvore(p):
    return set(S.arvore(p.pid)) if p.poll() is None else set()


def principal(p):
    """A janela principal do PokeNexus (título "PokeNexus", classe do Qt, com ou sem estar à vista)."""
    for h, t, c, _v in janelas(arvore(p)):
        if t == "PokeNexus" and c.startswith("Qt") and "Tray" not in c:
            return h
    return None


def J(p):
    """A janela principal AGORA: o Qt recria a janela nativa (HWND novo) quando as páginas entram nela."""
    return principal(p) or 0


def pid_app(p):
    """O processo que é o PokeNexus (o .exe; rodando do código, o python.exe filho do lançador do .venv)."""
    h = principal(p)
    if not h:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def janela_bandeja(pid):
    """A janela de mensagens do ícone da bandeja (o Explorer manda os cliques do ícone para ela)."""
    for h, _t, c, _v in janelas({pid}):
        if "TrayIconMessageWindow" in c:
            return h
    h = None
    while True:           # caso seja uma janela só de mensagens
        h = user32.FindWindowExW(wintypes.HWND(-3), h, None, None)
        if not h:
            return None
        pid_h = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid_h))
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if pid_h.value == pid and "TrayIconMessageWindow" in c.value:
            return h


def visivel(h):
    return bool(user32.IsWindowVisible(h))


def pronto(p, timeout=60):
    """Espera a janela principal aparecer (aberta e visível)."""
    return esperar(lambda: (h := principal(p)) and visivel(h) and h, timeout)


def icone(pid, evento):
    h = janela_bandeja(pid)
    user32.PostMessageW(h, MYWM_NOTIFYICON, (300 << 16) | 300, evento)   # HIWORD = id do ícone (0)


def tecla(h, vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = 1 << 24 if vk in (VK_UP, VK_DOWN) else 0
    user32.PostMessageW(h, WM_KEYDOWN, vk, 1 | (scan << 16) | ext)
    time.sleep(.05)
    user32.PostMessageW(h, WM_KEYUP, vk, 1 | (scan << 16) | ext | (3 << 30))
    time.sleep(.15)


def foto(nome, h=None, margem=0):
    tela = qapp.primaryScreen()
    if h:
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        img = tela.grabWindow(0, r.left - margem, r.top - margem, r.right - r.left + 2 * margem,
                              r.bottom - r.top + 2 * margem)
    else:             # canto de baixo à direita (onde o Windows mostra o aviso), não a tela inteira
        g = tela.geometry()
        img = tela.grabWindow(0, g.width() - 520, g.height() - 330, 520, 330)
    img.save(str(saida / f"{nome}.png"))


def fim_de_sessao(h):
    """O que o Windows manda ao desligar/sair da conta: WM_QUERYENDSESSION e WM_ENDSESSION."""
    r = ctypes.c_size_t()
    user32.SendMessageTimeoutW(h, WM_QUERYENDSESSION, 0, ENDSESSION_LOGOFF, 0x0002, 60000, ctypes.byref(r))
    user32.SendMessageTimeoutW(h, WM_ENDSESSION, 1, ENDSESSION_LOGOFF, 0x0002, 60000, ctypes.byref(r))
    return r.value


def terminou_sem_sobra(p, pids, timeout=60):
    """O processo saiu e nenhum dos processos dele (PokeNexus/python e QtWebEngineProcess) ficou."""
    try:
        p.wait(timeout)
    except subprocess.TimeoutExpired:
        return False, "não saiu"
    t = time.monotonic()
    vivos = esperar(lambda: not (set(S.processos()) & pids), 60, .5)
    todos = S.processos()
    sobra = {q: todos[q] for q in set(todos) & pids}
    if sobra:
        return False, f"sobrou {sobra} (pid: (pai, nome))"
    return bool(vivos), f"processos sumiram {time.monotonic() - t:.1f} s depois de sair"


def linhas_do_log(dados, trecho):
    logs = Path(dados) / "logs"
    return [l for f in logs.glob("*.log") for l in f.read_text(encoding="utf-8", errors="replace").splitlines()
            if trecho in l] if logs.exists() else []


def tempo_inicio(pid):
    h = k32.OpenProcess(0x1000, False, pid)
    c, x, kk, u = (wintypes.FILETIME() for _ in range(4))
    k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(kk), ctypes.byref(u))
    k32.CloseHandle(h)
    return c


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [("Process", RM_UNIQUE_PROCESS), ("strAppName", wintypes.WCHAR * 256),
                ("strServiceShortName", wintypes.WCHAR * 64), ("ApplicationType", ctypes.c_int),
                ("AppStatus", wintypes.ULONG), ("TSSessionId", wintypes.DWORD), ("bRestartable", wintypes.BOOL)]


def restart_manager(pid):
    """O Restart Manager do Windows fecha o processo como o instalador faz (CloseApplications, sem forçar)."""
    sessao = wintypes.DWORD()
    chave = ctypes.create_unicode_buffer(64)
    assert rm.RmStartSession(ctypes.byref(sessao), 0, chave) == 0
    try:
        proc = RM_UNIQUE_PROCESS(pid, tempo_inicio(pid))
        assert rm.RmRegisterResources(sessao, 0, None, 1, ctypes.byref(proc), 0, None) == 0
        precisa, n, motivo = wintypes.UINT(), wintypes.UINT(10), wintypes.DWORD()
        lista = (RM_PROCESS_INFO * 10)()
        rm.RmGetList(sessao, ctypes.byref(precisa), ctypes.byref(n), lista, ctypes.byref(motivo))
        tipos = [lista[i].ApplicationType for i in range(n.value)]
        t = time.monotonic()
        r = rm.RmShutdown(sessao, 0, None)
        return {"RmShutdown": r, "tipos": tipos, "segundos": round(time.monotonic() - t, 1)}
    finally:
        rm.RmEndSession(sessao)


def matar(pid):
    h = k32.OpenProcess(0x0001, False, pid)
    k32.TerminateProcess(h, 1)
    k32.CloseHandle(h)


try:
    # ------------------------------------------------ A: X, Alt+F4, clique, duplo clique, menu
    dados_a = nova_pasta()
    a = abrir(dados_a)
    pronto(a)
    registrar("abre_maximizada", user32.IsZoomed(J(a)))
    time.sleep(6)                      # deixa as contas começarem a abrir (tela de login)
    pid_a = pid_app(a)
    pids_a = arvore(a)

    user32.PostMessageW(J(a), WM_CLOSE, 0, 0)
    ok = esperar(lambda: not visivel(J(a)), 5)
    time.sleep(1.5)
    foto("1_aviso_balao")              # o balão do Windows na primeira ida para a bandeja
    registrar("x_esconde_e_processo_continua", ok and a.poll() is None)

    icone(pid_a, NIN_SELECT)
    ok = esperar(lambda: visivel(J(a)), 5)
    registrar("clique_no_icone_mostra_maximizada", ok and user32.IsZoomed(J(a)))

    user32.PostMessageW(J(a), WM_SYSCOMMAND, SC_CLOSE, 0)
    ok = esperar(lambda: not visivel(J(a)), 5)
    registrar("alt_f4_esconde", ok and a.poll() is None)

    # O que o Explorer manda num duplo clique: soltar do 1º clique, o duplo clique e o soltar do 2º (que o Qt
    # ignora de propósito). Só o duplo clique, sem o 3º, faria o Qt engolir o próximo clique simples.
    icone(pid_a, WM_LBUTTONDBLCLK)
    ok = esperar(lambda: visivel(J(a)), 5)
    icone(pid_a, NIN_SELECT)
    registrar("duplo_clique_mostra", ok and user32.IsZoomed(J(a)))

    # Minimizar também vai para a bandeja; o clique traz de volta maximizada.
    user32.PostMessageW(J(a), WM_SYSCOMMAND, SC_MINIMIZE, 0)
    ok = esperar(lambda: not visivel(J(a)), 5)
    icone(pid_a, NIN_SELECT)
    ok2 = esperar(lambda: visivel(J(a)) and not user32.IsIconic(J(a)), 5)
    registrar("minimizar_vai_para_bandeja_e_volta_maximizada", ok and ok2 and user32.IsZoomed(J(a)))

    # Janela NÃO maximizada: volta no mesmo tamanho e lugar.
    user32.PostMessageW(J(a), WM_SYSCOMMAND, SC_RESTORE, 0)
    esperar(lambda: not user32.IsZoomed(J(a)), 5)
    user32.MoveWindow(J(a), 120, 90, 1300, 820, True)       # tamanho e lugar próprios, longe do maximizado
    time.sleep(.8)
    antes = retangulo(J(a))
    user32.PostMessageW(J(a), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(a)), 5)
    icone(pid_a, NIN_SELECT)
    esperar(lambda: visivel(J(a)), 5)
    time.sleep(.5)
    depois = retangulo(J(a))
    registrar("janela_normal_volta_igual", not user32.IsZoomed(J(a)) and antes == depois, f"{antes} -> {depois}")
    user32.PostMessageW(J(a), WM_SYSCOMMAND, SC_MAXIMIZE, 0)
    esperar(lambda: user32.IsZoomed(J(a)), 5)

    # Segunda cópia com o programa escondido: mostra a janela da primeira e sai, sem abrir nada.
    user32.PostMessageW(J(a), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(a)), 5)
    t = time.monotonic()
    b = abrir(dados_a)
    try:
        cod = b.wait(30)
    except subprocess.TimeoutExpired:
        cod = None
    filhos_b = [n for n in S.arvore(b.pid).values()] if b.poll() is None else []
    ok = esperar(lambda: visivel(J(a)), 5)
    registrar("segunda_copia_mostra_a_primeira_e_sai",
              cod == 0 and ok and a.poll() is None and not filhos_b,
              f"saiu em {time.monotonic() - t:.1f} s com código {cod}")

    # Menu do botão direito: Abrir
    user32.PostMessageW(J(a), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(a)), 5)
    icone(pid_a, WM_CONTEXTMENU)
    menu = esperar(lambda: next((j for j, t_, c, v in janelas({pid_a}, True) if "Popup" in c), None), 5)
    if menu:
        time.sleep(.5)
        foto("2_menu_bandeja", menu, 6)
        tecla(menu, VK_DOWN)           # o status é só leitura: a primeira opção é "Abrir PokeNexus"
        tecla(menu, VK_RETURN)
    ok = esperar(lambda: visivel(J(a)), 5)
    registrar("menu_abrir", bool(menu) and ok)

    # Menu: Sair. Fecha de verdade e não sobra processo.
    user32.PostMessageW(J(a), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(a)), 5)
    pids_a |= arvore(a)
    icone(pid_a, WM_CONTEXTMENU)
    menu = esperar(lambda: next((j for j, t_, c, v in janelas({pid_a}, True) if "Popup" in c), None), 5)
    if menu:
        time.sleep(.3)
        tecla(menu, VK_UP)             # de baixo para cima: "Sair" é a última
        tecla(menu, VK_RETURN)
    ok, det = terminou_sem_sobra(a, pids_a)
    registrar("menu_sair_sem_sobrar_processo", bool(menu) and ok, det)

    # ------------------------------------------------ pastas de dados diferentes = independentes
    dados_c, dados_d = nova_pasta(), nova_pasta()
    c = abrir(dados_c)
    hc = pronto(c)
    d = abrir(dados_d)
    hd = pronto(d)
    registrar("pastas_de_dados_diferentes_abrem_juntas", bool(hc and J(d)) and c.poll() is None and d.poll() is None)
    time.sleep(5)
    pids_c, pids_d = arvore(c), arvore(d)

    # ------------------------------------------------ fim de sessão do Windows (com a janela escondida)
    user32.PostMessageW(J(c), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(c)), 5)
    t = time.monotonic()
    fim_de_sessao(J(c))
    ok, det = terminou_sem_sobra(c, pids_c)
    linhas = linhas_do_log(dados_c, "o Windows pediu para fechar")
    registrar("fim_de_sessao_sai_pelo_sair", ok and bool(linhas), f"{time.monotonic() - t:.1f} s; {det}")

    # ------------------------------------------------ Restart Manager (instalador) com a janela escondida
    pid_d = pid_app(d)
    user32.PostMessageW(J(d), WM_CLOSE, 0, 0)
    esperar(lambda: not visivel(J(d)), 5)
    r = restart_manager(pid_d)
    ok, det = terminou_sem_sobra(d, pids_d)
    linhas = linhas_do_log(dados_d, "o Windows pediu para fechar")
    registrar("restart_manager_do_instalador_fecha_escondido", r["RmShutdown"] == 0 and ok and bool(linhas),
              f"{json.dumps(r)}; {det}")

    # ------------------------------------------------ cópia anterior morta: abre na hora
    dados_e = nova_pasta()
    e = abrir(dados_e)
    pronto(e)
    time.sleep(3)
    pids_e = arvore(e)
    matar(pid_app(e))
    time.sleep(1)
    t = time.monotonic()
    e2 = abrir(dados_e)
    he2 = pronto(e2, 40)
    registrar("copia_morta_nao_impede_abrir", bool(he2), f"abriu em {time.monotonic() - t:.1f} s")
    sobra_e = esperar(lambda: not (set(S.processos()) & (pids_e - {e2.pid})), 20, .5)
    registrar("copia_morta_nao_deixa_processo", bool(sobra_e))

    # ------------------------------------------------ cópia anterior travada: pergunta, fecha e abre
    pid_e2 = pid_app(e2)
    pids_e2 = arvore(e2)
    hp = k32.OpenProcess(0x0800, False, pid_e2)          # PROCESS_SUSPEND_RESUME
    ntdll.NtSuspendProcess(hp)
    t = time.monotonic()
    e3 = abrir(dados_e)
    pids_e3_ini = lambda: arvore(e3) - pids_e2  # noqa: E731
    aviso = esperar(lambda: next((j for j, t_, c_, v in janelas(pids_e3_ini(), True)
                                  if t_ == "PokeNexus" and c_.startswith("Qt")), None), 40)
    espera_aviso = time.monotonic() - t
    if aviso:
        time.sleep(1)
        tecla(aviso, VK_TAB)           # foco sai do "Cancelar" (padrão) para "Fechar e abrir"
        tecla(aviso, VK_SPACE)
    he3 = esperar(lambda: (j := principal(e3)) and visivel(j) and j != aviso and j, 60)
    k32.CloseHandle(hp)
    registrar("copia_travada_pergunta_fecha_e_abre", bool(aviso and J(e3)) and e2.poll() is not None,
              f"aviso em {espera_aviso:.1f} s")
    sobra = esperar(lambda: not (set(S.processos()) & (pids_e2 - {e3.pid})), 20, .5)
    registrar("copia_travada_fechada_nao_deixa_processo", bool(sobra))
    pids_e3 = arvore(e3)
    fim_de_sessao(J(e3))
    ok, det = terminou_sem_sobra(e3, pids_e3)
    registrar("fim_de_sessao_com_janela_visivel", ok, det)
finally:
    for p in processos_abertos:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    (saida / "fluxos.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    falhas = [k for k, v in resultado.items() if not v["ok"]]
    print("FALHAS: " + ", ".join(falhas) if falhas else f"todos os {len(resultado)} fluxos ok", flush=True)
