"""Ícone da bandeja do Windows (perto do relógio).

O X da janela deixa o PokeNexus aqui, com as contas farmando. Clique (simples ou duplo) no ícone: a janela
volta. Botão direito: o status (só leitura), Abrir PokeNexus e Sair. O ciclo de vida (esconder, mostrar e
fechar de verdade) fica na janela principal: `MainWindow.enviar_bandeja`, `restaurar` e `sair`.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.tema import T

AVISO = "O PokeNexus continua rodando aqui. Para fechar, clique no ícone e em Sair."


def resumo(jogando: int, com_erro: int) -> str:
    """"4 contas jogando", "1 conta jogando, 1 com erro"..."""
    texto = ("Nenhuma conta jogando" if jogando == 0 else
             "1 conta jogando" if jogando == 1 else f"{jogando} contas jogando")
    if com_erro:
        texto += f", {com_erro} com erro"
    return texto


class Bandeja(QObject):
    abrir = Signal()
    sair = Signal()

    def __init__(self, janela):
        super().__init__(janela)
        self.icone = QSystemTrayIcon(janela.windowIcon(), self)
        # O menu é filho da janela: herda a folha de estilo do tema (QMenu em app/tema.py).
        self.menu = QMenu(janela)
        self.menu.setStyleSheet(f"QMenu::item:disabled {{ color: {T['dim']}; }}")
        self.status = self.menu.addAction(resumo(0, 0))
        self.status.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Abrir PokeNexus", self.abrir.emit)
        self.menu.addAction("Sair", self.sair.emit)
        self.icone.setContextMenu(self.menu)
        self.icone.setToolTip("PokeNexus")
        self.icone.activated.connect(self._ativada)
        self._avisou = False
        if self.disponivel:
            self.icone.show()

    @property
    def disponivel(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _ativada(self, motivo):
        if motivo in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.abrir.emit()

    def atualizar(self, jogando: int, com_erro: int):
        """Status da linha do menu e da dica. Só toca no ícone quando o texto muda."""
        texto = resumo(jogando, com_erro)
        if self.status.text() != texto:
            self.status.setText(texto)
            self.icone.setToolTip("PokeNexus\n" + texto)

    def avisar_primeira_vez(self):
        """O balão do Windows na primeira ida para a bandeja de cada sessão (nada gravado em disco)."""
        if self._avisou or not self.disponivel:
            return
        self._avisou = True
        self.icone.showMessage("PokeNexus", AVISO, self.icone.icon(), 8000)

    def fechar(self):
        self.icone.hide()
