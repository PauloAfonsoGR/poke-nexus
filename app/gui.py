"""Interface do PokeIdle Multi Manager (PySide6).

O jogo de cada conta aparece DENTRO da janela, na área principal (GameArea):
uma página Qt WebEngine por conta, todas vivas ao mesmo tempo num QStackedWidget.
Trocar de conta só troca qual página está à vista - nada recarrega.
"""
import collections
import html
import queue
import re
import time

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImageReader, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QBoxLayout, QCheckBox, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from app import config_edit
from app.bandeja import Bandeja
from app.config import APP_NAME, APP_VERSION, ASSETS_DIR, CONFIG_PATH, LIMITE_TERMOS, MODO_LEVE
from app.settings_ui import SettingsDialog
from app.hunt_ui import HuntPanel
from app.rmt_ui import RmtPanel
from app.manager import Manager
from app.atualizacao import Atualizacao
from app.pokedex_ui import PokedexDados, PokedexPanel, bola as pokedex_bola
from app.dialogos import avisar, perguntar
from app.erros_rede import traduzir as traduzir_erro
from app.molduras import Botao, Moldura
from app.icones import TAM as ICO_TAM, icone, por_nome_do_botao
from app.tema import T, carregar_fontes, qss
from app.widgets import (SPRITES, CheckerBackground, PixelSprite, StatusPill, _alpha_bbox,
                         pixel_pixmap, pokemon_path, status_color)
from browser.web_host import WebHost

YELLOW = T["destaque"]

ATIVOS = ("FARMING", "BATALHA", "MANUAL")
# status de uma conta ligada ao jogo (o contador do topo, com o servidor do jogo conectado)
JOGANDO = ("FARMING", "BATALHA", "AGUARDANDO", "MANUAL", "PAUSADO")
# Pokémon em campo que aparecem nas abas das contas (speciesId do jogo = nº da Pokédex).
INICIAIS = {1: "Bulbasaur", 4: "Charmander", 7: "Squirtle"}


def fmt_num(v) -> str:
    return "—" if v is None else f"{int(v):,}".replace(",", ".")


def fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec else "—"


def sprite_icon(dex: int, factor_half=True) -> QPixmap:
    """Primeiro quadro da sprite, recortado; metade do tamanho (2x2 -> 1 pixel)."""
    img = QImageReader(str(pokemon_path(dex))).read()
    if img.isNull():
        return QPixmap()
    r = _alpha_bbox(img)
    if r:
        img = img.copy(r)
    if factor_half:
        img = img.scaled(max(1, img.width() // 2), max(1, img.height() // 2),
                         Qt.KeepAspectRatio, Qt.FastTransformation)
    return QPixmap.fromImage(img)


def card(title: str | None = None, margins=(16, 14, 16, 16)) -> tuple[QFrame, QVBoxLayout]:
    f = Moldura()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("cardTitle")
        lay.addWidget(t)
    return f, lay


def button(text, obj=None, tip="", slot=None, ico=None) -> QPushButton:
    b = Botao((" " + text) if ico and text else text)
    if ico:
        b.setIcon(icone(ico, por_nome_do_botao(obj)))
        b.setIconSize(ICO_TAM)
        b.setProperty("ico", ico)
    b.setCursor(Qt.PointingHandCursor)
    if obj:
        b.setObjectName(obj)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    return b


# ============================================================ abas das contas
class AccountTab(Moldura):
    clicked = Signal(int)

    def __init__(self, info: dict, shortcut: str):
        super().__init__()
        self.index = info["index"]
        self.setObjectName("tab")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(185)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 8, 0)
        lay.setSpacing(8)
        self.sprite = PixelSprite(info["sprite"], 52)
        self._dex_padrao = self._dex = info["sprite"]
        lay.addWidget(self.sprite)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        self.name = QLabel(info["name"])
        self.name.setObjectName("tabName")
        key = QLabel(shortcut)
        key.setObjectName("atalho")
        top.addWidget(self.name)
        top.addStretch()
        top.addWidget(key)
        col.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.pill = StatusPill()
        row.addWidget(self.pill)
        self.sub = QLabel("—")
        self.sub.setObjectName("muted")
        self.sub.setStyleSheet("font-size:11px;")
        row.addWidget(self.sub)
        row.addStretch()
        col.addLayout(row)
        lay.addLayout(col, 1)
        if not info["enabled"]:
            self.setProperty("disabledacc", True)
            self.setToolTip("Desativada no config.toml (ativa = false)")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

    def set_selected(self, sel: bool):
        self.setProperty("selected", sel)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_conta(self, nome: str, sprite: int, ativa: bool):
        """Depois das Configurações: nome, mascote e conta ativa/desativada na hora."""
        self.name.setText(nome)
        if self._dex == self._dex_padrao and sprite != self._dex:
            self._dex = sprite
            self.sprite.set_dex(sprite)
        self._dex_padrao = sprite
        if bool(self.property("disabledacc")) == ativa:
            self.setProperty("disabledacc", not ativa)
            self.setToolTip("" if ativa else "Desativada no config.toml (ativa = false)")
            self.style().unpolish(self)
            self.style().polish(self)

    def update_info(self, s: dict):
        status = s["status"] if s["enabled"] else "OFFLINE"
        self.pill.set_status(status)
        # O pokémon sendo upado aparece na aba (só os 3 iniciais); senão, o mascote de sempre.
        ativo = s.get("ativo_especie")
        dex = ativo if ativo in INICIAIS else self._dex_padrao
        if dex != self._dex:
            self._dex = dex
            self.sprite.set_dex(dex)
            self.setToolTip(f"Upando agora: {INICIAIS[dex]}" if dex in INICIAIS and ativo == dex else "")
        self.sprite.set_active(status in ATIVOS)
        if not s["enabled"]:
            self.sub.setText("desativada")
        elif s["xp_h"] is not None:
            self.sub.setText(f"{fmt_num(s['xp_h'])} XP/h")
        elif s["level"] is not None:
            self.sub.setText(f"Nv {s['level']}")
        else:
            self.sub.setText("")


class AllTab(Moldura):
    """A aba "VER TODAS" (View All), no fim da barra de contas."""
    clicked = Signal(int)

    def __init__(self, shortcut: str):
        super().__init__()
        self.index = -1
        self.setObjectName("tab")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(185)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Mostra todas as contas ao mesmo tempo, cada uma com o seu jogo")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(icone("todas", "ouro").pixmap(ICO_TAM).scaled(
            40, 40, Qt.KeepAspectRatio, Qt.FastTransformation))
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        t = QLabel("Todas as contas")
        t.setObjectName("tabTitle")
        top.addWidget(t)
        top.addStretch()
        key = QLabel(shortcut)
        key.setObjectName("atalho")
        top.addWidget(key)
        col.addLayout(top)
        sub = QLabel("ver todas juntas")
        sub.setObjectName("muted")
        sub.setStyleSheet("font-size:11px;")
        col.addWidget(sub)
        lay.addLayout(col, 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

    def set_selected(self, sel: bool):
        self.setProperty("selected", sel)
        self.style().unpolish(self)
        self.style().polish(self)


class AccountBar(QWidget):
    """As contas lado a lado (+ VER TODAS); quebra em mais linhas quando a janela é estreita."""

    TAB_MIN = 185

    def __init__(self, tabs: list[AccountTab]):
        super().__init__()
        self.tabs = tabs
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self._cols = 0
        self.fit(10_000)

    def fit(self, width: int):
        n = len(self.tabs)
        cols = max(1, min(n, (width + 10) // (self.TAB_MIN + 10)))
        if cols == self._cols:
            return
        self._cols = cols
        for t in self.tabs:
            self.grid.removeWidget(t)
        for c in range(n):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        for i, t in enumerate(self.tabs):
            self.grid.addWidget(t, i // cols, i % cols)


# ============================================================ área do jogo
class Placeholder(QWidget):
    """O que aparece no lugar do jogo quando a conta não tem sessão aberta."""
    start = Signal()

    def __init__(self, dex: int):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addStretch()
        self.sprite = PixelSprite(dex, 120)
        self.sprite.set_active(False)
        lay.addWidget(self.sprite, 0, Qt.AlignHCenter)
        self.text = QLabel("")
        self.text.setObjectName("muted")
        self.text.setAlignment(Qt.AlignHCenter)
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.btn = button("Iniciar", "primary", slot=self.start.emit, ico="comecar")
        self.btn.setMinimumWidth(180)
        lay.addSpacing(4)
        lay.addWidget(self.btn, 0, Qt.AlignHCenter)
        lay.addStretch()

    def show_account(self, s: dict):
        if not s["enabled"]:
            self.text.setText(f"{s['name']} está desativada no config.toml (ativa = false).")
            self.btn.hide()
        elif s["running"] or s["login_open"]:
            # erro de rede em português; o código do Chromium fica na dica e o log guarda o original
            texto, dica = traduzir_erro(s["detail"] or "abrindo a sessão…")
            self.text.setText(texto)
            self.text.setToolTip(dica)
            self.btn.hide()
            return
        else:
            self.text.setText(f"{s['name']} está parada. Ao iniciar, o PokeIdle dela aparece aqui.")
            self.btn.setText(f" Iniciar {s['name']}")
            self.btn.show()
        self.text.setToolTip("")


class AccountCell(QFrame):
    """O "quadro" de uma conta: cabeçalho compacto (só no View All) + a página real do jogo.

    A página vive aqui do começo ao fim - trocar de modo só mostra/esconde/redimensiona o
    quadro, nunca move nem recarrega a página.
    """
    clicked = Signal(int)
    activated = Signal(int)     # duplo clique no cabeçalho: abre a conta na visão individual
    start = Signal(int)

    HEADER_H = 28

    def __init__(self, info: dict):
        super().__init__()
        self.index = info["index"]
        self.setObjectName("cell")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("cellHeader")
        self.header.setFixedHeight(self.HEADER_H)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setToolTip("Clique para selecionar. Duplo clique abre só esta conta.")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(6, 0, 6, 0)
        h.setSpacing(8)
        self.icon = QLabel()
        self.icon.setPixmap(sprite_icon(info["sprite"]).scaledToHeight(22, Qt.FastTransformation))
        h.addWidget(self.icon)
        self.name = QLabel(info["name"])
        self.name.setObjectName("cellName")
        h.addWidget(self.name)
        self.stats = QLabel("")
        self.stats.setObjectName("muted")
        self.stats.setStyleSheet("font-size:11px;")
        h.addWidget(self.stats)
        h.addStretch()
        self.pill = StatusPill()
        h.addWidget(self.pill)
        lay.addWidget(self.header)
        self.header.mousePressEvent = lambda e: self.clicked.emit(self.index)
        self.header.mouseDoubleClickEvent = lambda e: self.activated.emit(self.index)

        self.body = QStackedWidget()
        self.placeholder = Placeholder(info["sprite"])
        self.placeholder.start.connect(lambda: self.start.emit(self.index))
        self.body.addWidget(self.placeholder)
        lay.addWidget(self.body, 1)
        self.view: QWidget | None = None

    def set_view(self, view: QWidget | None):
        if self.view is not None:
            self.body.removeWidget(self.view)
        self.view = view
        if view is not None:
            self.body.addWidget(view)
            self.body.setCurrentWidget(view)
        else:
            self.body.setCurrentWidget(self.placeholder)

    def set_conta(self, nome: str, sprite: int):
        self.name.setText(nome)
        self.icon.setPixmap(sprite_icon(sprite).scaledToHeight(22, Qt.FastTransformation))
        self.placeholder.sprite.set_dex(sprite)
        self.placeholder.sprite.set_active(False)

    def set_grid(self, grid: bool, selected: bool):
        self.header.setVisible(grid)
        self.setProperty("grid", grid)
        self.setProperty("selected", grid and selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def update_info(self, s: dict):
        status = s["status"] if s["enabled"] else "OFFLINE"
        self.pill.set_status(status)
        partes = []
        if s["level"] is not None:
            partes.append(f"Nv {s['level']}")
        if s["xp_h"] is not None:
            partes.append(f"{fmt_num(s['xp_h'])} XP/h")
        self.stats.setText("\u2003".join(partes))
        if self.view is None:
            self.placeholder.show_account(s)


class CellsHost(QWidget):
    """Posiciona os quadros: um só (visão individual) ou todos em grade (View All)."""

    GAP = 8
    CSS_W, CSS_H = 1280, 720    # tamanho em que o PokeIdle fica confortável
    # "Celulares lado a lado": cada quadro em pé, como um celular. O PokeIdle liga sozinho o layout
    # de celular quando a página tem até 720 px CSS de largura (mobile.mjs, "(max-width: 720px)") e
    # volta ao de desktop quando passa disso — sem recarregar e sem fingir ser outro aparelho. Aqui
    # só se escolhe o tamanho do quadro e o zoom para a página ficar com ~412 px CSS.
    CEL_CSS_W = 412
    CEL_CSS_MAX = 700           # folga abaixo dos 720 do jogo
    CEL_PROPORCAO = 9 / 19.5    # largura / altura de um celular
    # O Market do jogo (1.300) tem altura fixa: 88% da página, até 864 px CSS. Com a página mais baixa
    # que 982 px CSS os cartões encolhem e o botão de comprar some (é do jogo: num navegador comum
    # acontece igual). Enquanto o Market está aberto numa página, o zoom dela desce o bastante para a
    # página ter essa altura; ao fechar, volta. Ver docs/visual/interface_1300.
    MARKET_CSS_H = 982

    def __init__(self, cells: list[AccountCell], zoom_for):
        super().__init__()
        self.cells = cells
        self.zoom_for = zoom_for    # zoom da visão individual de cada conta
        self.grid = False
        self.layout_todas = "grade"     # grade | celulares
        self.current = 0
        self.market: set[int] = set()   # contas com o Market do jogo aberto (lido da página)
        for c in cells:
            c.setParent(self)

    def _com_market(self, c: AccountCell, zoom: float, larg: int, alt: int) -> float:
        """O zoom do quadro, ou menos, se o Market do jogo estiver aberto e não couber. `larg` e `alt`:
        o tamanho da página em px da tela. Página estreita (layout de celular do jogo, até 720 px CSS)
        fica como está: lá o Market rola e não corta."""
        if c.index not in self.market or larg / zoom <= 720:
            return zoom
        return min(zoom, max(0.25, int(alt / self.MARKET_CSS_H * 100) / 100))

    def zoom_individual(self, c: AccountCell) -> float:
        # a página ocupa o quadro inteiro, menos a borda de 2 px (sem o cabeçalho, que é só do VER TODAS)
        return self._com_market(c, self.zoom_for(c.index), self.width() - 4, self.height() - 4)

    def set_layout_todas(self, layout: str):
        self.layout_todas = layout if layout in ("grade", "celulares") else "grade"
        self.relayout()

    def _celulares(self, w: int, h: int):
        n = len(self.cells)
        alt = h - AccountCell.HEADER_H
        cw = (w - self.GAP * (n - 1)) // n
        cw = max(120, min(cw, int(alt * self.CEL_PROPORCAO)))     # nunca mais largo que um celular
        x0 = max(0, (w - (cw * n + self.GAP * (n - 1))) // 2)      # o grupo fica no meio
        for k, c in enumerate(self.cells):
            c.setGeometry(x0 + k * (cw + self.GAP), 0, cw, h)
            c.set_grid(True, c.index == self.current)
            c.show()
            if c.view:
                # ~412 px CSS de largura; e nunca acima de 700 (senão o jogo volta ao desktop).
                zoom = max(cw / self.CEL_CSS_W, cw / self.CEL_CSS_MAX, 0.25)
                c.view.setZoomFactor(round(min(zoom, 3.0), 3))

    def set_mode(self, grid: bool, current: int):
        self.grid, self.current = grid, current
        self.relayout()

    def _grid_shape(self, n: int, w: int, h: int) -> int:
        """Quantas colunas deixam os quadros maiores (proporção do jogo, 16:9)."""
        best_cols, best = 1, -1.0
        for cols in range(1, n + 1):
            rows = -(-n // cols)
            cw = (w - self.GAP * (cols - 1)) / cols
            ch = (h - self.GAP * (rows - 1)) / rows - AccountCell.HEADER_H
            score = min(cw / 16, ch / 9)
            if score > best:
                best_cols, best = cols, score
        return best_cols

    def relayout(self):
        w, h = self.width(), self.height()
        if not self.grid:
            # As contas fora da tela ficam escondidas (o Qt não desenha a página delas). Como página
            # escondida não recebe tamanho, o jogo nelas monta o layout de celular — o farm e o
            # `enter_hunt` sabem lidar com os dois layouts.
            for c in self.cells:
                if c.index == self.current:
                    c.setGeometry(0, 0, w, h)
                    c.set_grid(False, True)
                    c.show()
                    if c.view:
                        c.view.setZoomFactor(self.zoom_individual(c))
                else:
                    c.hide()
            return
        if self.layout_todas == "celulares":
            return self._celulares(w, h)
        n = len(self.cells)
        cols = self._grid_shape(n, w, h)
        rows = -(-n // cols)
        ch = (h - self.GAP * (rows - 1)) // rows
        for r in range(rows):
            linha = self.cells[r * cols:(r + 1) * cols]
            # A última linha pode ter menos quadros: eles se esticam para ocupar a largura.
            cw = (w - self.GAP * (len(linha) - 1)) // len(linha)
            for k, c in enumerate(linha):
                c.setGeometry(k * (cw + self.GAP), r * (ch + self.GAP), cw, ch)
                c.set_grid(True, c.index == self.current)
                c.show()
                if c.view:
                    fit = min(cw / self.CSS_W, (ch - AccountCell.HEADER_H) / self.CSS_H)
                    c.view.setZoomFactor(self._com_market(c, round(min(1.0, max(0.3, fit)), 2),
                                                          cw - 4, ch - AccountCell.HEADER_H - 4))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()


class GameArea(Moldura):
    """A área principal: o PokeIdle real e interativo - de uma conta ou de todas."""
    start = Signal(int)
    selected = Signal(int)
    single = Signal(int)
    layout_todas = Signal(str)          # grade | celulares (escolhido na barra do VER TODAS)
    mostrar_painel = Signal()
    area_mudou = Signal(str)            # jogo | hunts | rmt | pokedex (o botão Pokédex do topo acompanha)

    def __init__(self, snap: list[dict], zoom: float):
        super().__init__()
        self.setObjectName("card")
        self.default_zoom = zoom
        self.zoom: dict[int, float] = {}
        self.current = 0
        self.grid = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 4)
        lay.setSpacing(2)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.icon = QLabel()
        bar.addWidget(self.icon)
        self.title = QLabel("")
        self.title.setObjectName("gameTitle")
        bar.addWidget(self.title)
        self.pill = StatusPill()
        bar.addWidget(self.pill)
        self.where = QLabel("")
        self.where.setObjectName("muted")
        bar.addWidget(self.where)
        bar.addStretch()
        # Jogo | Hunts: a mesma área mostra o jogo ou o Hunt Analyzer da conta selecionada.
        self.b_jogo = button("Jogo", "tool", "Mostra o jogo (Ctrl+H alterna)", lambda: self.set_hunts(False), ico="jogo")
        self.b_hunts = button("Hunts", "tool", "Hunt Analyzer: as melhores hunts para o pokémon em campo "
                              "desta conta (Ctrl+H alterna)", lambda: self.set_hunts(True), ico="hunts")
        self.b_rmt = button("Mercado", "tool", "Mercado da Comunidade (RMT): compra e venda automáticas desta "
                            "conta, com simulação e limites", lambda: self.set_area("rmt"), ico="rmt")
        for b in (self.b_jogo, self.b_hunts, self.b_rmt):
            b.setCheckable(True)
            bar.addWidget(b)
        # Só no VER TODAS: grade (como sempre) ou as contas em pé, lado a lado, como celulares.
        self.b_grade = button("Grade", "tool", "Todas as contas em grade, com o jogo de computador",
                              lambda: self.layout_todas.emit("grade"), ico="todas")
        self.b_cel = button("Celulares", "tool", "As contas em pé, lado a lado, cada uma no "
                            "layout de celular do próprio jogo (nada recarrega)", lambda: self.layout_todas.emit("celulares"),
                            ico="celulares")
        self.sep_layout = QLabel("")
        self.sep_layout.setObjectName("muted")
        bar.addSpacing(6)
        bar.addWidget(self.sep_layout)
        for b in (self.b_grade, self.b_cel):
            b.setCheckable(True)
            b.setVisible(False)
            bar.addWidget(b)
        self.sep_layout.setVisible(False)
        self.b_jogo.setChecked(True)
        bar.addSpacing(8)
        self.b_zoom_out = button("", "tool", "Diminuir o zoom do jogo", lambda: self.change_zoom(-0.1), ico="menos")
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setObjectName("muted")
        self.zoom_lbl.setMinimumWidth(40)
        self.zoom_lbl.setAlignment(Qt.AlignCenter)
        self.b_zoom_in = button("", "tool", "Aumentar o zoom do jogo", lambda: self.change_zoom(0.1), ico="mais")
        self.b_reload = button("", "tool", "Recarregar a página da conta selecionada", self.reload, ico="recarregar")
        for w in (self.b_zoom_out, self.zoom_lbl, self.b_zoom_in, self.b_reload):
            bar.addWidget(w)
        # Só aparece com o painel "Conta selecionada" escondido: mostra ele de novo.
        self.b_painel = button("Ficha", "tool", "Mostrar a ficha do treinador (Ctrl+B)",
                               lambda: self.mostrar_painel.emit(), ico="mostrar")
        self.b_painel.setVisible(False)
        bar.addWidget(self.b_painel)
        lay.addLayout(bar)
        # Janela estreita (1366×768 a 150%, janela no mínimo): em vez de cortar o texto, os botões de texto
        # da barra ficam só com o ícone. A dica no mouse continua dizendo o que cada um faz.
        self._bar = bar
        self._textos_barra = {b: b.text() for b in (self.b_jogo, self.b_hunts, self.b_rmt, self.b_grade, self.b_cel)}
        self._larg_cheia: dict = {}
        self._barra_curta = False

        self.cells = [AccountCell(s) for s in snap]
        for c in self.cells:
            c.start.connect(self.start.emit)
            c.clicked.connect(self.selected.emit)
            c.activated.connect(self.single.emit)
        self.host = CellsHost(self.cells, lambda i: self.zoom.get(i, self.default_zoom))
        self.hunt_panel = HuntPanel()
        self.rmt_panel = RmtPanel()
        self.body = QStackedWidget()
        self.body.addWidget(self.host)
        self.body.addWidget(self.hunt_panel)
        self.body.addWidget(self.rmt_panel)
        self.pokedex_panel = None          # só nasce quando a Pokédex é aberta pela primeira vez
        lay.addWidget(self.body, 1)
        self.area = "jogo"
        self.hunts = False
        self.setMinimumSize(560, 420)
        # O Market do jogo está aberto? Só LÊ a página (ver CellsHost.MARKET_CSS_H).
        self._market_timer = QTimer(self)
        self._market_timer.timeout.connect(self._olhar_market)
        self._market_timer.start(800)

    # true = o modal do Market do jogo está à vista, no layout de computador (o de celular rola sozinho)
    JS_MARKET = ("(() => { const m = document.getElementById('modal');"
                 " const c = m && !m.classList.contains('hidden') ? m.querySelector('.modal-caixa') : null;"
                 " return !!(c && c.dataset.modal === 'market'"
                 " && !document.documentElement.classList.contains('mobile')); })()")

    def _olhar_market(self):
        if self.area != "jogo" or (self.grid and self.host.layout_todas == "celulares"):
            return
        for c in self.cells:
            if c.view is not None and c.isVisible():
                c.view.page().runJavaScript(self.JS_MARKET, 0, lambda aberto, i=c.index: self._market(i, aberto))

    def _market(self, index: int, aberto):
        aberto = aberto is True
        if aberto == (index in self.host.market) or self.cells[index].view is None:
            return
        if aberto:
            self.host.market.add(index)
        else:
            self.host.market.discard(index)
        self.host.relayout()
        self._mostrar_zoom()

    def _ajustar_barra(self):
        """Os botões de texto da barra só com o ícone quando a barra não cabe na largura da área."""
        if not self.isVisible():
            return
        total, n = 0, 0
        for k in range(self._bar.count()):
            it = self._bar.itemAt(k)
            w = it.widget()
            if w is None:
                if it.spacerItem() is not None:          # addSpacing (o addStretch vale 0)
                    total += it.spacerItem().sizeHint().width()
                continue
            if w.isHidden():
                continue
            if w in self._textos_barra and not self._barra_curta:
                self._larg_cheia[w] = w.sizeHint().width()
            total += self._larg_cheia.get(w, w.sizeHint().width())
            n += 1
        m = self.layout().contentsMargins()
        curta = total + self._bar.spacing() * max(0, n - 1) > self.width() - m.left() - m.right()
        if curta != self._barra_curta:
            self._barra_curta = curta
            for b, texto in self._textos_barra.items():
                b.setText("" if curta else texto)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ajustar_barra()

    def _mostrar_zoom(self):
        """O zoom em uso na visão individual (com o Market aberto pode ser menor que o escolhido)."""
        if self.grid:
            texto, dica = "auto", ""
        else:
            escolhido = self.zoom.get(self.current, self.default_zoom)
            view = self.view(self.current)
            z = view.zoomFactor() if view is not None else escolhido
            texto = f"{round(z * 100)}%"
            dica = (f"Market do jogo aberto: zoom menor para os cartões caberem. Volta a "
                    f"{round(escolhido * 100)}% ao fechar." if z < escolhido - 0.004 else "")
        if self.zoom_lbl.text() != texto:
            self.zoom_lbl.setText(texto)
        if self.zoom_lbl.toolTip() != dica:
            self.zoom_lbl.setToolTip(dica)

    def set_area(self, area: str):
        """Jogo, Hunts, RMT ou Pokédex na área principal (as páginas do jogo continuam vivas por trás)."""
        if area == "pokedex" and self.pokedex_panel is None:
            return
        self.area = area
        self.hunts = area == "hunts"
        for b, a in ((self.b_jogo, "jogo"), (self.b_hunts, "hunts"), (self.b_rmt, "rmt")):
            b.setChecked(a == area)
        self.body.setCurrentWidget({"jogo": self.host, "hunts": self.hunt_panel, "rmt": self.rmt_panel,
                                    "pokedex": self.pokedex_panel}[area])
        for b in (self.b_zoom_in, self.b_zoom_out, self.zoom_lbl):
            b.setVisible(area == "jogo")
        self.area_mudou.emit(area)

    def set_pokedex(self, painel: QWidget):
        """A Pokédex entra na área principal na primeira vez que é aberta."""
        self.pokedex_panel = painel
        self.body.addWidget(painel)

    def set_hunts(self, on: bool):
        """Alterna entre o jogo e o Hunt Analyzer (Ctrl+H)."""
        self.set_area("hunts" if on else "jogo")

    # --------------------------------------------------------- páginas
    def add_view(self, index: int, view: QWidget):
        self.zoom.setdefault(index, self.default_zoom)
        self.host.market.discard(index)
        self.cells[index].set_view(view)
        self.host.relayout()

    def remove_view(self, index: int):
        self.host.market.discard(index)
        self.cells[index].set_view(None)

    def view(self, index: int) -> QWidget | None:
        return self.cells[index].view

    def cell_of(self, widget) -> int | None:
        """Qual conta contém este widget (para saber em que quadro a pessoa clicou)."""
        for c in self.cells:
            if c.view is not None and (widget is c.view or c.view.isAncestorOf(widget)):
                return c.index
        return None

    # ----------------------------------------------------------- modos
    def show_account(self, index: int, s: dict, grid: bool):
        self.current, self.grid = index, grid
        self.icon.setPixmap(sprite_icon(s["sprite"]))
        for w in (self.b_grade, self.b_cel, self.sep_layout):
            w.setVisible(grid)
        self.marcar_layout(self.host.layout_todas)
        self.host.set_mode(grid, index)
        self.update_info(s)

    def marcar_layout(self, layout: str):
        self.b_grade.setChecked(layout == "grade")
        self.b_cel.setChecked(layout == "celulares")

    def update_info(self, s: dict):
        self.title.setText(s["name"] if not self.grid else f"Todas as contas: {s['name']} selecionada")
        self.pill.set_status(s["status"] if s["enabled"] else "OFFLINE")
        partes = [p for p in (f"@{s['nick']}" if s["nick"] else "", s["hunt"] if s["hunt"] != "-" else "")
                  if p]
        self.where.setText("\u2003".join(partes))
        has_view = self.view(self.current) is not None
        # No View All o zoom é automático (cada quadro cabe no seu espaço).
        for b in (self.b_zoom_in, self.b_zoom_out):
            b.setEnabled(has_view and not self.grid)
        self.b_reload.setEnabled(has_view)
        self._mostrar_zoom()
        self._ajustar_barra()

    def update_cells(self, snap: list[dict]):
        for c, s in zip(self.cells, snap):
            c.update_info(s)

    def change_zoom(self, delta: float):
        view = self.view(self.current)
        if not view or self.grid:
            return
        z = min(2.0, max(0.5, round(self.zoom.get(self.current, 1.0) + delta, 2)))
        self.zoom[self.current] = z
        # com o Market do jogo aberto vale o menor: o escolhido ou o que faz o Market caber
        view.setZoomFactor(self.host.zoom_individual(self.cells[self.current]))
        self._mostrar_zoom()

    def reload(self):
        view = self.view(self.current)
        if view:
            view.reload()

    def focus_game(self):
        view = self.view(self.current)
        if view:
            view.setFocus(Qt.OtherFocusReason)


# ============================================================ conta selecionada
class Stage(QWidget):
    """O "palco" do mascote: um chão de grama em pixel, com a borda na cor do status."""

    W, H = 210, 168

    def __init__(self, sprite: PixelSprite):
        super().__init__()
        self.setFixedSize(self.W, self.H)
        self.sprite = sprite
        sprite.setParent(self)
        sprite.move((self.W - sprite.width()) // 2, 6)
        self.color = QColor(YELLOW)

    def paintEvent(self, _):
        # Retângulos inteiros, sem antialias: um tablado de grama com contorno, brilho em cima,
        # tufos e a "sombra" embaixo na cor do status (mesmo desenho no Modo Leve: nada se mexe).
        p = QPainter(self)
        x0, y0, w, h = 40, 134, self.W - 80, 22
        p.fillRect(x0 - 2, y0 - 2, w + 4, h + 4, QColor(T["filete"]))
        p.fillRect(x0, y0, w, h, QColor(T["chao"]))
        p.fillRect(x0, y0, w, 4, QColor(T["chao_luz"]))
        for k in range(6, w - 6, 18):               # tufos de grama
            p.fillRect(x0 + k, y0 - 4, 2, 4, QColor(T["chao_luz"]))
            p.fillRect(x0 + k + 4, y0 - 2, 2, 2, QColor(T["chao_luz"]))
        p.fillRect(x0, y0 + h - 4, w, 4, self.color)


class SidePanel(Moldura):
    action = Signal(str)

    STAT_KEYS = [("level", "Nível"), ("xp_h", "XP por hora"), ("xp", "XP ganho"), ("time", "Tempo ativo"),
                 ("battles", "Batalhas"), ("hunt", "Área"), ("last_battle", "Última batalha"),
                 ("last_action", "Última ação")]

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumWidth(300)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(8)

        cab = QHBoxLayout()
        t = QLabel("Ficha do treinador")
        t.setObjectName("cardTitle")
        # Recolhe o painel e o jogo ganha a largura dele (volta pelo "Ficha" na barra do jogo).
        self.b_recolher = button("", "tool", "Esconder a ficha: o jogo fica maior (volta pelo botão "
                                 "\"Ficha\" em cima do jogo, ou Ctrl+B)", lambda: self.action.emit("recolher"),
                                 ico="recolher")
        self.b_recolher.setFixedWidth(34)
        cab.addSpacing(34)                 # o mesmo espaço do botão, para o título ficar no meio
        cab.addStretch()
        cab.addWidget(t)
        cab.addStretch()
        cab.addWidget(self.b_recolher)
        lay.addLayout(cab)
        self.hero = PixelSprite(25, 144)
        self.stage = Stage(self.hero)
        lay.addWidget(self.stage, 0, Qt.AlignHCenter)
        self.name = QLabel("Conta")
        self.name.setObjectName("heroName")
        lay.addWidget(self.name, 0, Qt.AlignHCenter)
        self.nick = QLabel("")
        self.nick.setObjectName("muted")
        lay.addWidget(self.nick, 0, Qt.AlignHCenter)
        self.pill = StatusPill(big=True)
        lay.addWidget(self.pill, 0, Qt.AlignHCenter)
        self.detail = QLabel("")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignHCenter)
        self.detail.setMinimumHeight(32)
        lay.addWidget(self.detail)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.vals = {}
        for i, (k, label) in enumerate(self.STAT_KEYS):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            kl = QLabel(label)
            kl.setObjectName("statKey")
            vl = QLabel("—")
            vl.setObjectName("statVal")
            if k in ("last_battle", "last_action", "hunt"):
                vl.setObjectName("statTxt")
                vl.setWordWrap(True)
            cell.addWidget(kl)
            cell.addWidget(vl)
            grid.addLayout(cell, i // 2, i % 2)
            self.vals[k] = vl
        lay.addLayout(grid)
        lay.addSpacing(4)

        emit = lambda act: (lambda: self.action.emit(act))
        self.b_start = button("Iniciar", "primary", "Abre a sessão desta conta e começa o farm",
                              emit("start"), ico="comecar")
        self.b_manual = button("Jogar eu mesmo", None,
                               "Para a automação SÓ desta conta; você joga direto na tela ao lado",
                               emit("manual"), ico="mao")
        self.b_pause = button("Pausar", None, "Pausa a automação desta conta (F8)", emit("pause"), ico="pausar")
        self.b_resume = button("Retomar", "primary",
                               "Confere o estado atual do jogo e volta a automatizar (F8)", emit("resume"),
                               ico="recarregar")
        self.b_restart = button("Reiniciar", "danger", "Fecha e reabre a sessão desta conta",
                                emit("restart"), ico="reiniciar")
        self.b_login = button("Login", None, "Como entrar na conta", ico="chave")
        menu = QMenu(self.b_login)
        menu.addAction("Entrar aqui, na tela do jogo", lambda: self.action.emit("login_here"))
        menu.addAction("Entrar sem automação (se a verificação falhar)",
                       lambda: self.action.emit("login_window"))
        self.b_login.setMenu(menu)
        rows = [[self.b_start], [self.b_manual], [self.b_pause, self.b_resume],
                [self.b_restart, self.b_login]]
        for r in rows:
            h = QHBoxLayout()
            h.setSpacing(8)
            for b in r:
                h.addWidget(b)
            lay.addLayout(h)
        lay.addStretch()

    def set_account(self, s: dict):
        self.hero.set_dex(s["sprite"])
        self.name.setText(s["name"])

    def update_info(self, s: dict):
        status = s["status"]
        self.pill.set_status(status)
        self.hero.set_active(status in ATIVOS)
        cor = QColor(status_color(status) if status != "OFFLINE" else T["moldura_esc"])
        if cor != self.stage.color:
            self.stage.color = cor
            self.stage.update()
        self.nick.setText(f"@{s['nick']}" if s["nick"] else "")
        texto, dica = traduzir_erro(s["detail"] or "")
        self.detail.setText(texto)
        if self.detail.toolTip() != dica:
            self.detail.setToolTip(dica)
        v = self.vals
        v["level"].setText(fmt_num(s["level"]))
        v["xp_h"].setText(fmt_num(s["xp_h"]))
        v["xp"].setText(fmt_num(s["xp_gained"]))
        v["time"].setText(fmt_time(s["elapsed"]))
        v["battles"].setText(fmt_num(s["battles"]) if s["running"] else "—")
        v["hunt"].setText(s["hunt"])
        v["last_battle"].setText(s["last_battle"])
        v["last_action"].setText(s["last_action"])

        running, mode = s["running"], s["mode"]
        self.b_start.setText(" Parar" if running else
                             " Já entrei, iniciar" if s["login_open"] else " Iniciar")
        obj = "danger" if running else "primary"
        if self.b_start.objectName() != obj:
            self.b_start.setObjectName(obj)
            self.b_start.setIcon(icone("parar" if running else "comecar", por_nome_do_botao(obj)))
            self.b_start.style().unpolish(self.b_start)
            self.b_start.style().polish(self.b_start)
        self.b_start.setEnabled(s["enabled"])
        self.b_manual.setEnabled(running and mode != "manual")
        self.b_pause.setEnabled(running and mode == "auto")
        self.b_resume.setEnabled(running and mode != "auto")
        self.b_restart.setEnabled(running)
        self.b_login.setEnabled(s["enabled"] and not s["login_open"])


# ============================================================ janela principal
class MainWindow(QMainWindow):
    def __init__(self, manager: Manager, web: WebHost):
        super().__init__()
        self.m = manager
        self.web = web
        self.cfg = manager.cfg
        self._encerrando = False
        self._segundo_plano = False
        self.selected = 0
        self.grid_mode = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "pokenexus.ico")))
        self.bandeja = Bandeja(self)
        self.bandeja.abrir.connect(self.restaurar)
        self.bandeja.sair.connect(self.encerrar)
        self.resize(1600, 1000)
        self.setMinimumSize(760, 600)
        carregar_fontes()
        self.setStyleSheet(qss())
        # Modo Leve: menos linhas do log guardadas na tela (o arquivo de log continua igual).
        self._log_lines = collections.deque(maxlen=1000 if MODO_LEVE else 4000)
        self._atalhos: list[QShortcut] = []

        bg = CheckerBackground()
        self.setCentralWidget(bg)
        root = QVBoxLayout(bg)
        root.setContentsMargins(16, 12, 16, 10)
        root.setSpacing(10)

        self.header = self._build_header()
        root.addLayout(self.header)

        snap = self.m.snapshot()
        atalhos = self.cfg["atalhos"]
        self.tabs = [AccountTab(s, atalhos.get(f"conta_{s['index'] + 1}", "")) for s in snap]
        for t in self.tabs:
            t.clicked.connect(self.select)
        self.all_tab = AllTab(atalhos.get("ver_todas", ""))
        self.all_tab.clicked.connect(lambda _i: self.view_all())
        self.bar = AccountBar(self.tabs + [self.all_tab])
        root.addWidget(self.bar)

        # Centro: jogo (grande) + painel da conta. Embaixo: dashboard + log.
        self.game = GameArea(snap, self.cfg["janela"]["zoom"])
        self.game.start.connect(self._start_from_cell)
        hp = self.game.hunt_panel
        hp.pref.connect(lambda k, v: (self.m.hunt_set_pref(self.selected, k, v), self._render_hunts()))
        hp.cacar.connect(lambda slug: self.m.go_hunt(self.selected, slug))
        hp.recalcular.connect(lambda: self.m.hunt_refresh(self.selected, force=True))
        self.game.host.layout_todas = self.cfg["janela"].get("layout_ver_todas", "grade")
        self.game.layout_todas.connect(self._trocar_layout_todas)
        rp = self.game.rmt_panel
        rp.parar_todos.connect(self.m.rmt_parar_todos)
        # "Saldo de todas as contas" da calculadora: as Gemas que cada conta conectada já mostra (só lê)
        rp.saldos = lambda: [w.game.eu.get("orbs") if w.game and w.game.welcomed else None for w in self.m.workers]
        rp.set_convite(not self.cfg["janela"].get("guia_mercado_visto", False))
        rp.guia_visto.connect(self._guia_mercado_visto)
        # Pokédex (app/pokedex_ui.py): os dados vivem sempre (só guardam as espécies novas); a tela só nasce
        # quando a pessoa abre a Pokédex.
        self.pokedex = PokedexDados(self.m)
        self._pokedex_olhou = 0.0
        self.game.area_mudou.connect(lambda a: self.b_pokedex.setChecked(a == "pokedex"))
        self._hunt_pedido = 0.0
        self.game.selected.connect(lambda i: self.select(i, keep_mode=True))
        self.game.single.connect(self.select)
        QApplication.instance().focusChanged.connect(self._on_focus)
        self.side = SidePanel()
        self.side.action.connect(self._on_action)
        self.top_split = QSplitter(Qt.Horizontal)
        self.top_split.addWidget(self.game)
        self.top_split.addWidget(self.side)
        self.top_split.setStretchFactor(0, 1)
        self.top_split.setStretchFactor(1, 0)
        self.top_split.setChildrenCollapsible(False)
        self.top_split.setSizes([1240, 320])
        self.game.mostrar_painel.connect(lambda: self._painel_conta(True))
        self._painel_conta(bool(self.cfg["janela"].get("painel_conta", True)), salvar=False)

        self.bottom = QSplitter(Qt.Horizontal)
        self.bottom.addWidget(self._build_dashboard(snap))
        self.bottom.addWidget(self._build_log())
        self.bottom.setChildrenCollapsible(False)
        self.bottom.setSizes([800, 700])

        self.main_split = QSplitter(Qt.Vertical)
        self.main_split.addWidget(self.top_split)
        self.main_split.addWidget(self.bottom)
        self.main_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(1, 0)
        self.main_split.setChildrenCollapsible(False)
        self.main_split.setSizes([720, 230])
        root.addWidget(self.main_split, 1)
        # Em telas de até 1080p o jogo precisa da altura toda: dashboard e log começam escondidos.
        tela = self.screen().availableGeometry().height() if self.screen() else 1000
        self.b_bottom.setChecked(tela >= 1200)
        self.bottom.setVisible(tela >= 1200)

        self.foot = QLabel(self._texto_rodape(len(snap)))
        self.foot.setObjectName("muted")
        self.foot.setStyleSheet("font-size:11px;")
        self.foot.setWordWrap(True)
        root.addWidget(self.foot)

        self.web.view_added.connect(self.game.add_view)
        self.web.view_removed.connect(self.game.remove_view)

        self._shortcuts(len(snap))
        # Aviso de atualização (app/atualizacao.py): uma faixa abaixo do topo, escondida sem versão nova.
        self.atualizacao = Atualizacao(self, self.m, lambda faixa: root.insertWidget(1, faixa))
        self.select(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        # Modo Leve: a tela se atualiza a cada 1 s (os comandos continuam imediatos).
        self.timer.start(1000 if MODO_LEVE else 500)
        self.refresh()
        if self.cfg["iniciar_contas_ao_abrir"]:
            QTimer.singleShot(800, lambda: self.m.start_all() if not self._encerrando else None)
        if self.cfg["janela"].get("iniciar_na_bandeja"):
            QTimer.singleShot(0, self.enviar_bandeja)

    def _trocar_layout_todas(self, layout: str, salvar: bool = True):
        """Grade ou celulares no VER TODAS: só muda o tamanho dos quadros e o zoom (nada recarrega)."""
        self.game.host.set_layout_todas(layout)
        self.game.marcar_layout(self.game.host.layout_todas)
        if salvar and self.cfg["janela"].get("layout_ver_todas") != layout:
            self.cfg["janela"]["layout_ver_todas"] = layout
            try:
                config_edit.salvar_um(CONFIG_PATH, "janela", "layout_ver_todas", layout)
            except (OSError, config_edit.ErroConfig):
                pass

    def _guia_mercado_visto(self):
        """Já viu (ou dispensou) o guia do Mercado: o convite não aparece mais."""
        if self.cfg["janela"].get("guia_mercado_visto"):
            return
        self.cfg["janela"]["guia_mercado_visto"] = True
        try:
            config_edit.salvar_um(CONFIG_PATH, "janela", "guia_mercado_visto", True)
        except (OSError, config_edit.ErroConfig):
            pass

    def _alternar_rmt(self):
        self.game.set_area("jogo" if self.game.area == "rmt" else "rmt")
        if self.game.area == "rmt":
            self.game.rmt_panel.render(self.selected, self.m.workers[self.selected])

    def _alternar_pokedex(self):
        """Abre a Pokédex na área do jogo (ou volta para o jogo). Ela só mostra: não mexe no jogo."""
        if self.game.area == "pokedex":
            self.game.set_area("jogo")
            return
        if self.game.pokedex_panel is None:
            self.game.set_pokedex(PokedexPanel(self.pokedex, lambda: [a.name for a in self.m.accounts]))
        self.pokedex.observar()
        p = self.game.pokedex_panel
        p.mostrar(self.selected)
        p.recarregar()
        self.game.set_area("pokedex")

    def _texto_rodape(self, n: int) -> str:
        partes = [f"{APP_NAME} {APP_VERSION}", "Ferramenta não oficial"]
        if MODO_LEVE:
            partes.append("Modo Leve")
        partes.append("F1: atalhos e ajuda")
        return "\u2003\u2003".join(partes)

    def _ajuda(self):
        """Ajuda (F1): os atalhos e as regras do jogo que antes ficavam no rodapé."""
        a = self.cfg["atalhos"]
        n = len(self.tabs)
        linhas = [
            "Contas: use os botões no topo; os atalhos configurados aparecem nas dicas",
            f"{a.get('ver_todas', 'Ctrl+0')}: todas as contas",
            f"{a.get('hunts', 'Ctrl+H')}: jogo ou Hunts",
            f"{a.get('rmt', 'Ctrl+M')}: jogo ou Mercado",
            f"{a.get('pokedex', config_edit.ATALHO_PADRAO['pokedex'])}: jogo ou Pokédex",
            f"{a.get('pausar_retomar', 'F8')}: pausar ou retomar a conta",
            f"{a.get('painel_conta', 'Ctrl+B')}: mostrar ou esconder a ficha",
            f"{a.get('configuracoes', 'Ctrl+,')}: ajustes",
            "",
            "A automação é permitida pelos Termos do PokeIdle, com no máximo "
            f"{LIMITE_TERMOS} contas por pessoa. O servidor também limita rede e aparelho.",
            "O limite local em Ajustes não altera o limite do servidor.",
            "Na bandeja: Abrir PokeNexus ou Sair e parar as contas.",
            "Os atalhos mudam em Ajustes.",
            "",
            "Erro de conexão só no PokeNexus?",
            "Se o PokeIdle abre no navegador, troque o DNS do Windows:",
            "1. Win+R, digite ncpa.cpl e Enter.",
            "2. Botão direito no adaptador da internet, Propriedades.",
            "3. Protocolo IP Versão 4 (TCP/IPv4), Propriedades.",
            "4. Em cima, Obter um endereço IP automaticamente. Embaixo, Usar os seguintes endereços de "
            "servidor DNS: 1.1.1.1 e 8.8.8.8. OK.",
            "5. No Prompt de Comando: ipconfig /flushdns",
            "Para testar, desative também adaptadores de VPN (ex.: Radmin) no ncpa.cpl.",
        ]
        avisar(self, "Atalhos e ajuda", "\n".join(linhas))

    # ------------------------------------------------------- configurações
    def open_settings(self):
        """Janela de Configurações. Ela não mexe nas páginas do jogo: as contas seguem farmando
        enquanto está aberta (o loop das contas e a atualização da tela continuam)."""
        if getattr(self, "_settings", None) is not None:
            self._settings.raise_()
            return
        self._settings = SettingsDialog(self, self.cfg, self.m.accounts)
        self._settings.salvo.connect(self._aplicar_config)
        try:
            self._settings.exec()
        finally:
            self._settings = None

    def _aplicar_config(self, valores: dict, contas: list[dict]):
        """Aplica na hora o que pode valer na hora (o resto vale na próxima abertura)."""
        for (sec, k), v in valores.items():
            if sec is None:
                if k in ("max_simultaneas", "intervalo_inicio_segundos"):
                    self.cfg[k] = v
            elif sec in ("intervalos", "farm", "atalhos", "atualizacao"):
                self.cfg[sec][k] = v          # os workers leem estes dicionários a cada uso
            elif (sec, k) == ("janela", "layout_ver_todas"):
                self.cfg["janela"][k] = v
                self._trocar_layout_todas(v, salvar=False)
            elif (sec, k) in (("janela", "fechar_para_bandeja"), ("janela", "minimizar_para_bandeja"),
                              ("desempenho", "economia_em_segundo_plano")):
                self.cfg[sec][k] = v
        for acc, c in zip(self.m.accounts, contas):
            acc.name, acc.sprite, acc.hunt, acc.enabled = c["nome"].strip(), c["sprite"], c["hunt"], c["ativa"]
        snap = self.m.snapshot()
        for t, cell, s in zip(self.tabs, self.game.cells, snap):
            t.set_conta(s["name"], s["sprite"], s["enabled"])
            cell.set_conta(s["name"], s["sprite"])
            it = self.table.item(s["index"], 0)
            it.setText("  " + s["name"])
            it.setIcon(sprite_icon(s["sprite"]))
        self._shortcuts(len(snap))
        self.foot.setText(self._texto_rodape(len(snap)))
        self.select(self.selected, keep_mode=True)
        self.refresh()

    # ---------------------------------------------------------- construção
    def _build_header(self):
        outer = QBoxLayout(QBoxLayout.LeftToRight)
        outer.setSpacing(12)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(pixel_pixmap(SPRITES / "ui" / "poke_ball.png", 2))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        b = QLabel("PokeNexus")
        b.setObjectName("brand")
        s = QLabel(f"base do treinador, {len(self.m.accounts)} contas")
        s.setObjectName("brandSub")
        col.addWidget(b)
        col.addWidget(s)
        brand.addLayout(col)
        brand.addStretch()
        outer.addLayout(brand)
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addStretch()
        self.counter = QLabel()
        self.counter.setObjectName("counter")
        h.addWidget(self.counter)
        # Pokédex no lugar onde ficava o "N/4 conectadas" (escolha do usuário, 17/10/2026): o contador fica à
        # esquerda dela, igual. Não confundir com o botão Pokédex do próprio jogo (dentro da página).
        atalho_dex = self.cfg["atalhos"].get("pokedex", config_edit.ATALHO_PADRAO["pokedex"])
        self.b_pokedex = button("Pokédex", None, f"A Pokédex do PokeNexus: quem esta conta já capturou "
                                f"({atalho_dex}). Só mostra, não mexe no jogo", self._alternar_pokedex)
        self.b_pokedex.setText(" Pokédex")
        self.b_pokedex.setIcon(QIcon(pokedex_bola("bola_botao.png")))     # a Great Ball (escolha do usuário)
        self.b_pokedex.setIconSize(ICO_TAM)
        self.b_pokedex.setCheckable(True)
        h.addWidget(self.b_pokedex)
        self._topo, self._marca = h, brand
        self._topo_curto = False
        self.b_bottom = button("Registro", None, "Mostra/esconde o dashboard e o log "
                               "(esconder deixa mais espaço para o jogo)", ico="log")
        self.b_bottom.setCheckable(True)
        self.b_bottom.toggled.connect(lambda on: self.bottom.setVisible(on))
        h.addWidget(self.b_bottom)
        # As pastas (dados, perfis, logs) abrem por dentro das Configurações.
        atalho = self.cfg["atalhos"].get("configuracoes", "Ctrl+,")
        h.addWidget(button("Ajustes", None, f"Opções do programa, pastas (dados, perfis e logs) e "
                           f"Modo Leve ({atalho}). Abrir não para nenhuma conta", self.open_settings, ico="config"))
        h.addWidget(button("Começar tudo", "primary", slot=self.m.start_all, ico="comecar"))
        h.addWidget(button("Parar tudo", "danger", slot=self._stop_all, ico="parar"))
        outer.addLayout(h)
        return outer

    def _build_dashboard(self, snap):
        f, lay = card("Contas", margins=(14, 10, 14, 10))
        cols = ["CONTA", "STATUS", "NÍVEL", "XP GANHO", "XP/H", "TEMPO", "BATALHAS", "ÚLT. BATALHA"]
        t = QTableWidget(len(snap), len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setIconSize(QSize(32, 32))
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(len(cols) - 1, QHeaderView.Stretch)
        hh.setMinimumSectionSize(54)
        t.setTextElideMode(Qt.ElideRight)
        for r, s in enumerate(snap):
            t.setRowHeight(r, 36)
            t.setItem(r, 0, QTableWidgetItem(sprite_icon(s["sprite"]), "  " + s["name"]))
            for c in range(1, len(cols)):
                t.setItem(r, c, QTableWidgetItem("—"))
        t.cellClicked.connect(lambda r, _c: self.select(r))
        self.table = t
        lay.addWidget(t)
        f.setMinimumHeight(140)
        return f

    def _build_log(self):
        f, lay = card(margins=(14, 10, 14, 10))
        top = QHBoxLayout()
        title = QLabel("Registro")
        title.setObjectName("cardTitle")
        top.addWidget(title)
        top.addStretch()
        self.f_sel = QCheckBox("Só conta selecionada")
        self.f_bat = QCheckBox("Mostrar batalhas")
        self.f_bat.setChecked(True)
        for cb in (self.f_sel, self.f_bat):
            cb.toggled.connect(self._rerender_log)
            top.addWidget(cb)
        lay.addLayout(top)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500 if MODO_LEVE else 2000)
        lay.addWidget(self.log)
        f.setMinimumHeight(140)
        return f

    def _shortcuts(self, n):
        """Cria (ou recria, depois das Configurações) os atalhos de teclado."""
        for sc in self._atalhos:
            sc.setEnabled(False)
            sc.deleteLater()
        self._atalhos = []
        a = self.cfg["atalhos"]
        pares = [(a.get(f"conta_{i + 1}"), lambda i=i: self.select(i)) for i in range(n)]
        pares += [(a.get("ver_todas"), self.view_all),
                  (a.get("pausar_retomar", "F8"), self._toggle_pause),
                  (a.get("hunts", "Ctrl+H"), lambda: self.game.set_hunts(not self.game.hunts)),
                  (a.get("rmt", "Ctrl+M"), self._alternar_rmt),
                  (a.get("pokedex", config_edit.ATALHO_PADRAO["pokedex"]), self._alternar_pokedex),
                  (a.get("configuracoes", "Ctrl+,"), self.open_settings),
                  (a.get("painel_conta", "Ctrl+B"), lambda: self._painel_conta(self.side.isHidden())),
                  ("F1", self._ajuda)]
        for seq, slot in pares:
            if seq:
                sc = QShortcut(QKeySequence(seq), self)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(slot)
                self._atalhos.append(sc)

    # -------------------------------------------------------------- ações
    def select(self, i: int, keep_mode: bool = False):
        """Seleciona a conta. Por padrão volta para a visão individual dela; com
        keep_mode=True (clique num quadro do View All) só troca a conta selecionada."""
        if not 0 <= i < len(self.tabs):
            return
        if not keep_mode:
            self.grid_mode = False
        changed = i != self.selected
        self.selected = i
        self.m.selected = i
        for t in self.tabs:
            t.set_selected(t.index == i)
        self.all_tab.set_selected(self.grid_mode)
        self.table.selectRow(i)
        s = self.m.snapshot()[i]
        self.game.show_account(i, s, self.grid_mode)
        self.side.set_account(s)
        self.side.update_info(s)
        if self.f_sel.isChecked() and changed:
            self._rerender_log()
        if self.game.hunts:
            self.m.hunt_refresh(i)
            self._render_hunts()
        if self.game.area == "rmt":
            self.game.rmt_panel.render(i, self.m.workers[i])
        if self.game.area == "pokedex":
            self.game.pokedex_panel.mostrar(i)

    def view_all(self):
        """View All: todas as contas na tela ao mesmo tempo (as mesmas páginas, sem recarregar)."""
        self.grid_mode = True
        self.select(self.selected, keep_mode=True)

    def _on_focus(self, _old, new):
        # Clicou dentro do jogo de um quadro do View All: essa conta passa a ser a selecionada.
        if self.grid_mode and new is not None:
            i = self.game.cell_of(new)
            if i is not None and i != self.selected:
                self.select(i, keep_mode=True)

    def _stop_all(self):
        n = sum(1 for s in self.m.snapshot() if s["running"] or s["login_open"])
        if not n:
            return
        if perguntar(self, "Parar tudo?", f"As {n} contas conectadas param de caçar agora. Dá para "
                     f"começar de novo quando quiser.", sim="Parar", nao="Cancelar", perigo=True):
            self.m.stop_all()

    def _render_hunts(self):
        s = self.m.snapshot()[self.selected]
        self.game.hunt_panel.render(self.selected, s["name"], self.m.hunt_view(self.selected))

    def _start_from_cell(self, i: int):
        if i != self.selected:
            self.select(i, keep_mode=True)
        self._on_action("start")

    def _painel_conta(self, visivel: bool, salvar: bool = True):
        """Mostra/esconde o painel "Conta selecionada" (na visão de uma conta e no VER TODAS). O jogo
        só muda de tamanho — nenhuma página recarrega. A escolha fica salva para a próxima abertura."""
        self.side.setVisible(visivel)
        self.game.b_painel.setVisible(not visivel)
        if salvar and self.cfg["janela"].get("painel_conta", True) != visivel:
            self.cfg["janela"]["painel_conta"] = visivel
            try:
                config_edit.salvar_um(CONFIG_PATH, "janela", "painel_conta", visivel)
            except (OSError, config_edit.ErroConfig):
                pass

    def _on_action(self, act: str):
        if act == "recolher":
            self._painel_conta(False)
            return
        i = self.selected
        s = self.m.snapshot()[i]
        if act == "start":
            if s["running"]:
                self.m.stop_account(i)
            else:
                ok, motivo = self.m.start_account(i)
                if not ok:
                    avisar(self, "Não foi possível iniciar", motivo, "aviso")
        elif act == "manual":
            self.m.take_manual(i)
            self.game.focus_game()
        elif act == "pause":
            self.m.pause(i)
        elif act == "resume":
            self.m.resume(i)
        elif act == "restart":
            self.m.restart_account(i)
        elif act == "login_here":
            if not s["running"]:
                ok, motivo = self.m.start_account(i)
                if not ok:
                    avisar(self, "Login", motivo, "aviso")
                    return
            avisar(
                self, "Login",
                "Faça o login direto na tela do jogo, à esquerda:\n\n"
                "1. Digite o usuário (ou e-mail) e a senha.\n"
                "2. Marque \"Confirme que é humano\".\n"
                "3. Clique em LOGAR.\n\n"
                "O login fica salvo no perfil desta conta e o farm começa sozinho.\n"
                "Se a verificação falhar, use \"Login\" e depois \"Entrar sem automação\".")
            self.game.focus_game()
        elif act == "login_window":
            if s["running"] and not perguntar(
                    self, "Login", "A automação desta conta será parada enquanto você faz o login. "
                                   "Continuar?"):
                return
            ok, motivo = self.m.open_login(i)
            if not ok:
                avisar(self, "Login", motivo, "aviso")
            else:
                avisar(
                    self, "Login",
                    "O jogo desta conta abre na tela, SEM monitoramento nem automação.\n\n"
                    "1. Entre na sua conta do PokeIdle.\n"
                    "2. Espere o jogo carregar.\n"
                    "3. Clique em \"Já entrei, iniciar\" na ficha ao lado.")
                self.game.focus_game()

    def _toggle_pause(self):
        s = self.m.snapshot()[self.selected]
        if not s["running"]:
            return
        if s["mode"] == "auto":
            self.m.pause(self.selected)
        else:
            self.m.resume(self.selected)

    # ----------------------------------------------------------- atualização
    def refresh(self):
        if self._segundo_plano:
            self._drain_logs(render=False)
            self.pokedex.observar()
            self.bandeja.atualizar(self.m.connected_count(), len(self.m.accounts))
            return
        snap = self.m.snapshot()
        for t, s in zip(self.tabs, snap):
            t.update_info(s)
        cur = snap[self.selected]
        self.side.update_info(cur)
        self.game.update_info(cur)
        self.game.update_cells(snap)
        for r, s in enumerate(snap):
            status = s["status"] if s["enabled"] else "OFFLINE"
            vals = [status, fmt_num(s["level"]), fmt_num(s["xp_gained"]), fmt_num(s["xp_h"]),
                    fmt_time(s["elapsed"]), fmt_num(s["battles"]) if s["running"] else "—",
                    s["last_battle"]]
            for c, v in enumerate(vals, start=1):
                it = self.table.item(r, c)
                if it.text() != v:
                    it.setText(v)
            st = self.table.item(r, 1)
            cor = QColor(status_color(status))
            if st.foreground().color() != cor:
                st.setForeground(cor)
            if not st.font().bold():
                f = st.font()
                f.setBold(True)
                st.setFont(f)
        self._mostrar_contador()
        self._drain_logs()
        if self.game.hunts:
            # Só a conta com a aba Hunts aberta é analisada; o analisador ignora o pedido se
            # nada que entra no cálculo mudou.
            agora = time.monotonic()
            if agora - self._hunt_pedido > 1.5:
                self._hunt_pedido = agora
                self.m.hunt_refresh(self.selected)
            self._render_hunts()
        elif self.game.area == "rmt":
            self.game.rmt_panel.render(self.selected, self.m.workers[self.selected])
        # Pokédex: a cada 2 s, guarda as espécies novas de cada conta (barato: só a conta que mudou faz a conta).
        agora = time.monotonic()
        if agora - self._pokedex_olhou >= 2:
            self._pokedex_olhou = agora
            novos = self.pokedex.observar()
            if self.game.area == "pokedex":
                p = self.game.pokedex_panel
                if self.pokedex.atualizar_catalogo():
                    p.recarregar()
                p.capturou(novos)

    def resizeEvent(self, e):
        """Adapta o layout à largura da janela."""
        super().resizeEvent(e)
        if not hasattr(self, "game"):
            return
        w = e.size().width()
        self.bar.fit(w - 32)
        self.top_split.setOrientation(Qt.Vertical if w < 900 else Qt.Horizontal)
        self.bottom.setOrientation(Qt.Vertical if w < 900 else Qt.Horizontal)
        self.header.setDirection(QBoxLayout.TopToBottom if w < 820 else QBoxLayout.LeftToRight)
        self._ajustar_topo(w)

    def _ajustar_topo(self, w: int):
        """Janela estreita (ex.: 760×600): o topo não comporta tudo com a Pokédex. Aí a Pokédex fica só com o
        ícone (a dica diz o que é) e o contador vira "N/4" (dica: contas conectadas). Os outros não mudam."""
        h = self._topo
        largos = [h.itemAt(k).widget() for k in range(h.count()) if h.itemAt(k).widget()]
        outros = sum(x.sizeHint().width() for x in largos if x not in (self.counter, self.b_pokedex))
        fm = self.counter.fontMetrics()
        cont = fm.horizontalAdvance(f"{len(self.m.accounts)}/{self.cfg['max_simultaneas']} jogando") + 28
        dex = self.b_pokedex.fontMetrics().horizontalAdvance(" Pokédex") + 50
        lugar = w - 32 - (0 if w < 820 else self._marca.sizeHint().width() + self.header.spacing())
        curto = outros + cont + dex + h.spacing() * (len(largos) - 1) > lugar
        if curto == self._topo_curto:
            return
        self._topo_curto = curto
        self.b_pokedex.setText("" if curto else " Pokédex")
        self._mostrar_contador()

    def _mostrar_contador(self):
        """O topo conta só as contas jogando de verdade (ligadas ao servidor do jogo: farm, batalha, esperando,
        manual ou pausada). Conta iniciada que não conectou (ex.: erro de rede) não entra. O limite dos Termos
        continua sendo conferido pelo Manager.connected_count/can_connect, que contam as iniciadas."""
        jogando = sum(1 for w in self.m.workers
                      if w.running and w.game is not None and w.game.welcomed and w.status in JOGANDO)
        iniciadas = self.m.connected_count()
        com_erro = sum(1 for w in self.m.workers if w.running and w.status == "ERRO")
        login = sum(1 for w in self.m.workers if w.login_open or (w.running and w.status == "SESSÃO EXPIRADA"))
        lim = self.cfg["max_simultaneas"]
        self.counter.setText(f"{jogando}/{lim}" if self._topo_curto else f"{jogando}/{lim} jogando")
        dica = (f"Jogando agora: {jogando}\nIniciadas: {iniciadas}\nCom erro: {com_erro}\n"
                + (f"Esperando o login: {login}\n" if login else "")
                + f"Limite local: {lim} sessões. Padrão do serviço: {LIMITE_TERMOS} por pessoa/rede")
        if self.counter.toolTip() != dica:
            self.counter.setToolTip(dica)
        cor = f"color:{T['erro'] if com_erro else T['aviso'] if iniciadas >= lim else T['destaque']};"
        if self.counter.styleSheet() != cor:      # setStyleSheet refaz o estilo mesmo sem mudar nada
            self.counter.setStyleSheet(cor)

    def _drain_logs(self, render=True):
        while True:
            try:
                line = self.m.logs.get_nowait()
            except queue.Empty:
                break
            self._log_lines.append(line)
            if render and self._passes(line):
                self.log.appendHtml(self._fmt(line))

    def _passes(self, line: str) -> bool:
        if not self.f_bat.isChecked() and re.search(r" - batalha (iniciada|concluída)", line):
            return False
        if self.f_sel.isChecked():
            return f"] {self.m.accounts[self.selected].name} - " in line
        return True

    def _rerender_log(self):
        self.log.clear()
        for line in self._log_lines:
            if self._passes(line):
                self.log.appendHtml(self._fmt(line))

    def _fmt(self, line: str) -> str:
        m = re.match(r"(\[\d\d:\d\d:\d\d\]) (.+?) - (.*)", line)
        if not m:
            return html.escape(line)
        ts, who, msg = (html.escape(x) for x in m.groups())
        color = T["texto"]
        low = msg.lower()
        if any(k in low for k in ("erro", "falha", "travado", "recusou", "expirad", "nocaute", "pausada para")):
            color = T["erro"]
        elif "batalha concluída" in low:
            color = T["ok"]
        elif "batalha iniciada" in low:
            color = T["dim"]
        elif any(k in low for k in ("reconect", "recarregando", "conexão perdida")):
            color = T["info"]
        elif "manual" in low:
            color = T["foco"]
        return (f'<span style="color:{T['apagado']}">{ts}</span> <span style="color:{YELLOW};font-weight:700">'
                f'{who}</span> <span style="color:{color}">- {msg}</span>')

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            if self.isMinimized() and self.cfg["janela"].get("minimizar_para_bandeja", True):
                QTimer.singleShot(0, lambda: self.enviar_bandeja() if self.isMinimized() else None)
            self._sincronizar_segundo_plano()
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._sincronizar_segundo_plano()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sincronizar_segundo_plano()

    def _sincronizar_segundo_plano(self):
        if not hasattr(self, "timer") or self._encerrando:
            return
        ativo = not self.isVisible() or self.isMinimized()
        self._segundo_plano = ativo
        PixelSprite.pausar_todas(ativo)
        self.m.set_background(ativo)
        self.timer.setInterval(5000 if ativo else (1000 if MODO_LEVE else 500))
        if not ativo:
            self._rerender_log()
            self.refresh()

    def enviar_bandeja(self):
        if not self._encerrando and self.bandeja.disponivel:
            self.bandeja.icone.show()
            self.hide()

    def restaurar(self):
        if self._encerrando:
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def encerrar(self):
        self._encerrando = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, e):
        if (not self._encerrando and self.cfg["janela"].get("fechar_para_bandeja", True)
                and self.bandeja.disponivel):
            e.ignore()
            self.enviar_bandeja()
            return
        self._encerrando = True
        self.timer.stop()
        self.bandeja.fechar()
        self.setEnabled(False)
        self.m.shutdown()
        self.web.close_all()
        e.accept()
