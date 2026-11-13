"""Teste rápido do ícone da bandeja (app/bandeja.py), sem páginas nem contas.

    .venv\\Scripts\\python.exe ferramentas\\bandeja\\teste_bandeja.py

Confere: o aviso (balão) só na primeira vez de cada sessão, os textos do status e da dica, o menu (status só
leitura, Abrir, Sair, sem emoji) e que clique e duplo clique pedem para abrir.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget  # noqa: E402

from app.bandeja import AVISO, Bandeja, resumo  # noqa: E402
from app.config import ASSETS_DIR  # noqa: E402

app = QApplication([])
janela = QWidget()
janela.setWindowIcon(QIcon(str(ASSETS_DIR / "pokenexus.ico")))
b = Bandeja(janela)
avisos = []
b.icone.showMessage = lambda *a: avisos.append(a)
pedidos = []
b.abrir.connect(lambda: pedidos.append("abrir"))
b.sair.connect(lambda: pedidos.append("sair"))

assert b.disponivel, "sem bandeja nesta sessão do Windows"
assert b.icone.isVisible(), "o ícone aparece desde que o programa abre"
assert not b.icone.icon().isNull()

b.avisar_primeira_vez()
b.avisar_primeira_vez()
b.avisar_primeira_vez()
assert len(avisos) == 1 and avisos[0][1] == AVISO, avisos

assert resumo(0, 0) == "Nenhuma conta jogando"
assert resumo(1, 0) == "1 conta jogando"
assert resumo(4, 0) == "4 contas jogando"
assert resumo(3, 1) == "3 contas jogando, 1 com erro"
b.atualizar(4, 0)
assert b.icone.toolTip() == "PokeNexus\n4 contas jogando"
assert b.status.text() == "4 contas jogando"
b.atualizar(2, 2)
assert b.icone.toolTip() == "PokeNexus\n2 contas jogando, 2 com erro"

textos = [a.text() for a in b.menu.actions() if not a.isSeparator()]
assert textos == ["2 contas jogando, 2 com erro", "Abrir PokeNexus", "Sair"], textos
assert not b.menu.actions()[0].isEnabled(), "o status é só leitura"
assert all(t.isascii() or all(ord(ch) < 0x2000 for ch in t) for t in textos), "sem emoji"
b.menu.actions()[2].trigger()
b.menu.actions()[3].trigger()
b.icone.activated.emit(QSystemTrayIcon.Trigger)
b.icone.activated.emit(QSystemTrayIcon.DoubleClick)
b.icone.activated.emit(QSystemTrayIcon.Context)          # botão direito só abre o menu
assert pedidos == ["abrir", "sair", "abrir", "abrir"], pedidos
b.fechar()
assert not b.icone.isVisible()
print("bandeja ok: aviso 1x por sessão, status, dica, menu, clique e duplo clique")
