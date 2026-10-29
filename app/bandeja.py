"""Ícone de bandeja e comandos; o ciclo de vida continua na janela principal."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Bandeja(QObject):
    abrir = Signal()
    sair = Signal()

    def __init__(self, janela):
        super().__init__(janela)
        self.icone = QSystemTrayIcon(janela.windowIcon(), self)
        self.menu = QMenu(janela)
        self.menu.addAction("Abrir PokeNexus", self.abrir.emit)
        self.menu.addSeparator()
        self.menu.addAction("Sair e parar as contas", self.sair.emit)
        self.icone.setContextMenu(self.menu)
        self.icone.setToolTip("PokeNexus")
        self.icone.activated.connect(self._ativada)
        if self.disponivel:
            self.icone.show()

    @property
    def disponivel(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _ativada(self, motivo):
        if motivo in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.abrir.emit()

    def atualizar(self, conectadas: int, total: int):
        self.icone.setToolTip(f"PokeNexus: {conectadas}/{total} sessões iniciadas")

    def fechar(self):
        self.icone.hide()
