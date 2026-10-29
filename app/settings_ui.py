"""Janela ⚙ Configurações: as opções do config.toml, as pastas (perfis, dados, logs) e o Modo Leve.

É uma janela de diálogo (e não uma página na área do jogo) de propósito: ela não toca nas páginas
das contas — nada é movido, escondido ou recarregado, as contas seguem farmando e, ao fechar, a
tela volta exatamente como estava. Nada é gravado até clicar em Salvar.
"""
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImageReader, QKeySequence, QPixmap
from PySide6.QtWidgets import (QSizePolicy, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QKeySequenceEdit, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app import config_edit
from app.config import (APP_VERSION, CONFIG_PATH, DATA_DIR, DEFAULT_SPRITES, DEFAULTS, LOGS_DIR, MODO_LEVE,
                        PROFILES_DIR, SPRITES_POKEMON, load_config)
from app.config_edit import CAMPOS, NOMES_ATALHOS, ErroConfig
from app.dialogos import avisar, perguntar
from app.molduras import Botao, Moldura
from app.icones import TAM as ICO_TAM, icone
from app.tema import T, carregar_fontes, qss_dialogo
from app.widgets import _alpha_bbox, travar_roda

YELLOW = T["destaque"]


def _estilo() -> str:
    carregar_fontes()
    return qss_dialogo() + f"""
QLabel#caminho {{ color: {T['dim']}; font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; }}
QLabel#selo {{ color: {T['dim']}; background: {T['trilho']}; border: 2px solid {T['filete']};
    padding: 0px 6px; font-size: 11px; font-weight: 700; }}
QLabel#erroMsg {{ color: {T['erro']}; font-weight: 700; }}
"""


def _icone(dex: int) -> QPixmap:
    p = SPRITES_POKEMON / f"{dex}.gif"
    img = QImageReader(str(p)).read() if p.is_file() else None
    if img is None or img.isNull():
        return QPixmap()
    r = _alpha_bbox(img)
    if r:
        img = img.copy(r)
    return QPixmap.fromImage(img).scaledToHeight(32, Qt.FastTransformation)


class SettingsDialog(QDialog):
    salvo = Signal(object, object)       # (valores {(seção, chave): valor}, contas [dict])

    def __init__(self, parent, cfg: dict, accounts, path: Path = CONFIG_PATH):
        super().__init__(parent)
        self.setWindowTitle("Ajustes do PokeNexus")
        self.setStyleSheet(_estilo())
        # 880×780, ou menos numa tela sem esse espaço livre (1366×768, escala de 150%): o conteúdo rola por
        # dentro, e o Salvar não pode ficar atrás da barra de tarefas (48 px: a barra de título e a borda).
        tela = (parent.screen() if parent is not None else QGuiApplication.primaryScreen()).availableGeometry()
        self.resize(min(880, tela.width() - 16), min(780, tela.height() - 48))
        self.path = path
        self.accounts = accounts
        # O que está no arquivo agora (pode ter coisas que só valem na próxima abertura).
        self.cfg_arquivo, self.contas_arquivo = load_config(path) if path.exists() else (cfg, accounts)
        self.cfg_rodando = cfg
        self.abrir_pasta = lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        self.copiar = lambda t: QGuiApplication.clipboard().setText(t)
        self.campos: dict = {}           # nome do campo (o de ErroConfig) -> widget
        self.widgets_contas: list[dict] = []

        fora = QVBoxLayout(self)
        fora.setContentsMargins(16, 14, 16, 12)
        topo = QLabel("Ajustes")
        topo.setObjectName("cardTitle")
        fora.addWidget(topo)
        sub = QLabel(f"Arquivo: {path}. As contas continuam farmando com esta janela aberta.")
        sub.setObjectName("muted")
        sub.setStyleSheet("font-size:11px;")
        sub.setWordWrap(True)
        fora.addWidget(sub)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.NoFrame)
        corpo = QWidget()
        rolagem.setWidget(corpo)
        self.rolagem = rolagem
        self.lay = QVBoxLayout(corpo)
        self.lay.setContentsMargins(0, 6, 8, 6)
        self.lay.setSpacing(12)
        fora.addWidget(rolagem, 1)

        self._pastas()
        self._geral()
        self._intervalos()
        self._farm()
        self._contas()
        self._atalhos()
        self._desempenho()
        self._atualizacao()
        self.lay.addStretch()
        travar_roda(corpo, rolagem.verticalScrollBar())

        base = QHBoxLayout()
        self.erro = QLabel("")
        self.erro.setObjectName("erroMsg")
        self.erro.setWordWrap(True)
        base.addWidget(self.erro, 1)
        cancelar = Botao("Cancelar")
        cancelar.clicked.connect(self.reject)
        self.b_salvar = Botao(" Salvar")
        self.b_salvar.setIcon(icone("salvar", "escuro"))
        self.b_salvar.setIconSize(ICO_TAM)
        self.b_salvar.setObjectName("primary")
        self.b_salvar.clicked.connect(self.salvar)
        base.addWidget(cancelar)
        base.addWidget(self.b_salvar)
        fora.addLayout(base)
        self._carregar(self.cfg_arquivo, self.contas_arquivo)

    # ------------------------------------------------------------ montagem
    def _card(self, titulo: str, padrao=None) -> QGridLayout:
        f = Moldura()
        f.setObjectName("card")
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel(titulo)
        t.setObjectName("cardTitle")
        cab.addWidget(t)
        cab.addStretch()
        if padrao:
            b = Botao("Restaurar padrão")
            b.setObjectName("tool")
            b.setToolTip("Volta os valores desta seção para o padrão (só grava ao clicar em Salvar)")
            b.clicked.connect(lambda: self._restaurar(titulo, padrao))
            cab.addWidget(b)
        v.addLayout(cab)
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        self.lay.addWidget(f)
        return g

    @staticmethod
    def _selo(sec, k):
        na_hora = CAMPOS[(sec, k)][3]
        l = QLabel("vale na hora" if na_hora else "vale ao reiniciar o app")
        l.setObjectName("selo")
        return l

    def _linha(self, g, rot: str, w: QWidget, sec, k, dica=""):
        r = g.rowCount()
        l = QLabel(rot)
        if dica:
            l.setToolTip(dica)
            w.setToolTip(dica)
        g.addWidget(l, r, 0)
        g.addWidget(w, r, 1)
        g.addWidget(self._selo(sec, k), r, 2, Qt.AlignVCenter)
        self.campos[f"{sec}.{k}" if sec else k] = w

    def _spin(self, sec, k, sufixo="", passo=1):
        _t, mn, mx, _ = CAMPOS[(sec, k)]
        s = QSpinBox()
        s.setRange(mn, mx if mx is not None else 2_147_483_647)
        s.setSingleStep(passo)
        s.setSuffix(sufixo)
        return s

    def _pastas(self):
        g = self._card("Pastas")
        linhas = [("Perfis de todas as contas", PROFILES_DIR, "perfis")]
        linhas += [(f"Perfil da {a.name}", a.profile_dir, f"perfil_{a.index}") for a in self.accounts]
        linhas += [("Pasta de dados (config, perfis, logs)", DATA_DIR, "dados"), ("Logs", LOGS_DIR, "logs")]
        self.botoes_pasta = {}
        for rot, p, chave in linhas:
            r = g.rowCount()
            l = QLabel(rot)
            if chave == "perfis":
                l.setStyleSheet("font-weight:800;")
            g.addWidget(l, r, 0)
            cam = QLabel(str(p))
            cam.setObjectName("caminho")
            cam.setTextInteractionFlags(Qt.TextSelectableByMouse)
            cam.setToolTip(str(p))
            cam.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            cam.setMinimumWidth(120)
            g.addWidget(cam, r, 1)
            bc = Botao(" Copiar")
            bc.setIcon(icone("copiar"))
            bc.setIconSize(ICO_TAM)
            bc.setObjectName("tool")
            bc.setToolTip("Copia o caminho")
            bc.clicked.connect(lambda _c=False, p=p: self.copiar(str(p)))
            ba = Botao(" Abrir")
            ba.setIcon(icone("pasta", "escuro" if chave == "perfis" else "claro"))
            ba.setIconSize(ICO_TAM)
            ba.setObjectName("primary" if chave == "perfis" else "tool")
            ba.clicked.connect(lambda _c=False, p=p: self._abrir(p))
            g.addWidget(bc, r, 2)
            g.addWidget(ba, r, 3)
            self.botoes_pasta[chave] = ba
        aviso = QLabel("Nos perfis ficam os logins (cookies e LocalStorage) de cada conta: não envie essas "
                       "pastas para ninguém. Para recomeçar uma conta do zero, feche o programa e apague a "
                       "pasta dela.")
        aviso.setObjectName("muted")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("font-size:11px;")
        g.addWidget(aviso, g.rowCount(), 0, 1, 4)

    def _abrir(self, p: Path):
        p.mkdir(parents=True, exist_ok=True)
        self.abrir_pasta(p)

    def _geral(self):
        g = self._card("Geral", "geral")
        self.w_iniciar = QCheckBox("Iniciar as contas ativas ao abrir o programa")
        self._linha(g, "Ao abrir", self.w_iniciar, None, "iniciar_contas_ao_abrir")
        self.w_max = self._spin(None, "max_simultaneas", " contas")
        self._linha(g, "Máximo conectadas ao mesmo tempo", self.w_max, None, "max_simultaneas",
                    "Limite do programa. O servidor pode recusar contas por IP/rede, independentemente deste valor")
        self.w_qtd = self._spin(None, "quantidade_contas", " contas")
        self._linha(g, "Contas no programa", self.w_qtd, None, "quantidade_contas")
        self.w_inicio_intervalo = self._spin(None, "intervalo_inicio_segundos", " s")
        self._linha(g, "Intervalo entre partidas", self.w_inicio_intervalo, None, "intervalo_inicio_segundos")
        self.w_bandeja = {}
        for chave, texto in (("fechar_para_bandeja", "Fechar no X mantém as contas na bandeja"),
                             ("minimizar_para_bandeja", "Minimizar envia para a bandeja"),
                             ("iniciar_na_bandeja", "Abrir o programa na bandeja")):
            w = QCheckBox(texto)
            self.w_bandeja[chave] = w
            self._linha(g, "", w, "janela", chave)
        self.w_zoom = QDoubleSpinBox()
        self.w_zoom.setRange(0.5, 2.0)
        self.w_zoom.setSingleStep(0.1)
        self.w_zoom.setDecimals(2)
        self._linha(g, "Zoom inicial do jogo", self.w_zoom, "janela", "zoom",
                    "1,0 = 100%. Também dá para mudar na hora pelos botões − e + em cima do jogo")
        self.w_layout = QComboBox()
        self.w_layout.addItem("Grade (jogo de computador)", "grade")
        self.w_layout.addItem("Celulares lado a lado (layout de celular do jogo)", "celulares")
        self._linha(g, "Todas as contas", self.w_layout, "janela", "layout_ver_todas",
                    "Também dá para trocar no próprio VER TODAS, na barra de cima")

    def _intervalos(self):
        g = self._card("Intervalos", "intervalos")
        self.w_int = {}
        for k, rot in (("verificacao_segundos", "Conferir o estado do jogo a cada"),
                       ("sem_resposta_recarregar_segundos", "Sem resposta do servidor → recarregar após"),
                       ("sem_batalha_recarregar_segundos", "Na hunt sem batalha → recarregar após"),
                       ("espera_volta_automatica_segundos", "Esperar a volta automática do jogo por")):
            s = self._spin("intervalos", k, " s")
            self.w_int[k] = s
            self._linha(g, rot, s, "intervalos", k)

    def _farm(self):
        g = self._card("Farm", "farm")
        self.w_farm = {}
        for k, rot, tipo, extra in (
                ("voltar_apos_derrota", "Voltar para a hunt depois de um nocaute", bool, None),
                ("max_derrotas", "Pausar a conta depois de", int, " nocautes"),
                ("janela_derrotas_minutos", "…dentro de", int, " min"),
                ("log_cada_batalha", "Escrever cada batalha no log", bool, None),
                ("reabrir_navegador", "Reabrir a sessão sozinho se a página travar", bool, None),
                ("limite_memoria_pagina_mb", "Reabrir a página acima de", int, " MB"),
                ("avancar_melhor_hunt", "Avançar para a melhor hunt segura", bool, None),
                ("objetivo_hunt", "Otimizar o farm para", str,
                 (("XP do Pokémon", "xp_pokemon"), ("XP do treinador", "xp_treinador"), ("Ouro", "ouro"))),
                ("risco_maximo_hunt", "Risco máximo aceito", str,
                 (("Baixo", "baixo"), ("Médio", "medio"))),
                ("usar_medicoes_reais", "Aprender com o ritmo real de cada hunt", bool, None),
                ("reavaliar_hunt_minutos", "Reavaliar a melhor hunt a cada", int, " min"),
                ("ganho_minimo_troca_pct", "Trocar somente com ganho mínimo de", int, "%")):
            if tipo is bool:
                w = QCheckBox(rot)
                self._linha(g, "", w, "farm", k)
            elif tipo is str:
                w = QComboBox()
                for texto, valor in extra:
                    w.addItem(texto, valor)
                self._linha(g, rot, w, "farm", k,
                            "Define a métrica e o risco usados pelo modo de rendimento máximo")
            else:
                w = self._spin("farm", k, extra, 100 if k == "limite_memoria_pagina_mb" else 1)
                if k == "limite_memoria_pagina_mb":
                    w.setSpecialValueText("desligado")
                dica = ("0 = desligado. Só reabre no farm automático, entre uma batalha e outra"
                        if k == "limite_memoria_pagina_mb" else
                        "Usa o ranking do Hunt Analyzer; respeita nível, risco e hunt fixa"
                        if k in ("avancar_melhor_hunt", "reavaliar_hunt_minutos", "ganho_minimo_troca_pct") else "")
                self._linha(g, rot, w, "farm", k,
                            dica)
            self.w_farm[k] = w

    def _contas(self):
        g = self._card("Contas", "contas")
        for col, t in enumerate(("", "Nome", "Mascote (nº da Pokédex)", "", "Hunt fixa", "Ativa")):
            l = QLabel(t)
            l.setObjectName("statKey")
            g.addWidget(l, 0, col)
        for i, a in enumerate(self.accounts):
            r = i + 1
            g.addWidget(QLabel(f"{i + 1}."), r, 0)
            nome = QLineEdit()
            nome.setMaxLength(30)
            sprite = QSpinBox()
            sprite.setRange(1, 386)
            previa = QLabel()
            previa.setFixedSize(40, 34)
            previa.setAlignment(Qt.AlignCenter)
            sprite.valueChanged.connect(lambda v, l=previa: l.setPixmap(_icone(v)))
            hunt = QLineEdit()
            hunt.setPlaceholderText("última hunt")
            hunt.setToolTip("Código do mapa (ex.: rota_1). Vazio = a última hunt em que a conta caçou")
            ativa = QCheckBox()
            for col, w in enumerate((nome, sprite, previa, hunt, ativa), start=1):
                g.addWidget(w, r, col)
            for k, w in (("nome", nome), ("sprite", sprite), ("hunt", hunt), ("ativa", ativa)):
                self.campos[f"contas.{i}.{k}"] = w
            self.widgets_contas.append({"nome": nome, "sprite": sprite, "previa": previa, "hunt": hunt,
                                        "ativa": ativa})
        nota = QLabel("Nome, mascote, hunt e ativa valem na hora (uma conta que já está farmando continua "
                      "até ser parada). Login, e-mail e senha nunca ficam aqui — só no perfil de cada conta.")
        nota.setObjectName("muted")
        nota.setWordWrap(True)
        nota.setStyleSheet("font-size:11px;")
        g.addWidget(nota, g.rowCount(), 0, 1, 6)

    def _atalhos(self):
        g = self._card("Atalhos", "atalhos")
        self.w_atalhos = {}
        for k in config_edit.ATALHOS:
            w = QKeySequenceEdit()
            if hasattr(w, "setMaximumSequenceLength"):
                w.setMaximumSequenceLength(1)
            if hasattr(w, "setClearButtonEnabled"):
                w.setClearButtonEnabled(True)
            r = g.rowCount()
            g.addWidget(QLabel(NOMES_ATALHOS[k]), r, 0)
            g.addWidget(w, r, 1)
            l = QLabel("vale na hora")
            l.setObjectName("selo")
            g.addWidget(l, r, 2, Qt.AlignVCenter)
            self.campos[f"atalhos.{k}"] = w
            self.w_atalhos[k] = w

    def _desempenho(self):
        g = self._card("Desempenho", "desempenho")
        self.w_economia = QCheckBox("Usar a economia do jogo enquanto estiver em segundo plano")
        self._linha(g, "", self.w_economia, "desempenho", "economia_em_segundo_plano",
                    "Desliga a cena pelo botão do jogo e restaura ao voltar. As batalhas continuam")
        self.w_leve = QCheckBox("Modo Leve")
        self._linha(g, "", self.w_leve, "desempenho", "modo_leve")
        txt = ("Tudo funciona igual (farm, VER TODAS, controle manual, Hunt Analyzer, atalhos), só a aparência "
               "fica mais simples: sprites paradas, selos sem piscar, fundo liso, tela atualizada a cada 1 s, "
               "e \"reduzir movimento\" nas páginas do jogo (o próprio CSS do PokeIdle desliga as animações "
               "de enfeite). Usa a placa de vídeo quando o PC tem uma; sem placa, desenha pelo modo mais "
               "barato para a CPU.\n"
               "Dica: o PokeIdle também tem o Modo Economia nas configurações do jogo (desliga a cena do "
               "mapa); a opção acima pode ativá-lo enquanto a janela estiver escondida.")
        aviso = QLabel("⚠  Para ligar ou desligar o Modo Leve, salve e REINICIE o PokeNexus (feche e abra "
                       "de novo): ele só é aplicado quando o programa abre.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color:{YELLOW}; font-weight:700;")
        g.addWidget(aviso, g.rowCount(), 1, 1, 2)
        estado = QLabel(f"Agora: {'ligado' if MODO_LEVE else 'desligado'}")
        estado.setObjectName("muted")
        g.addWidget(estado, g.rowCount(), 1)
        d = QLabel(txt)
        d.setObjectName("muted")
        d.setWordWrap(True)
        d.setStyleSheet("font-size:11px;")
        g.addWidget(d, g.rowCount(), 0, 1, 3)

    def _atualizacao(self):
        g = self._card("Atualização", "atualizacao")
        self.w_avisar = QCheckBox("Avisar quando tiver atualização")
        self._linha(g, "", self.w_avisar, "atualizacao", "avisar",
                    "Procura uma versão nova no GitHub ao abrir e a cada 6 horas. Nada é baixado sem você "
                    "clicar em Atualizar")
        b = Botao(" Procurar atualização agora")
        b.setIcon(icone("recarregar"))
        b.setIconSize(ICO_TAM)
        b.setObjectName("tool")
        dono = self.parent()
        b.clicked.connect(lambda: dono.atualizacao.procurar_agora(self) if hasattr(dono, "atualizacao") else None)
        g.addWidget(b, g.rowCount(), 1, Qt.AlignLeft)
        txt = QLabel(f"Versão instalada: {APP_VERSION}. Os logins e a configuração não mudam ao atualizar.")
        txt.setObjectName("muted")
        txt.setWordWrap(True)
        txt.setStyleSheet("font-size:11px;")
        g.addWidget(txt, g.rowCount(), 0, 1, 3)

    # ------------------------------------------------------------ valores
    def _carregar(self, cfg: dict, contas, secoes=None):
        """Põe os valores nos campos (secoes=None: todas)."""
        quer = (lambda s: secoes is None or s in secoes)
        if quer("geral"):
            self.w_iniciar.setChecked(bool(cfg["iniciar_contas_ao_abrir"]))
            self.w_max.setValue(int(cfg["max_simultaneas"]))
            self.w_qtd.setValue(int(cfg["quantidade_contas"]))
            self.w_inicio_intervalo.setValue(int(cfg["intervalo_inicio_segundos"]))
            for chave, w in self.w_bandeja.items():
                w.setChecked(bool(cfg["janela"][chave]))
            self.w_zoom.setValue(float(cfg["janela"]["zoom"]))
            i = self.w_layout.findData(cfg["janela"].get("layout_ver_todas", "grade"))
            self.w_layout.setCurrentIndex(max(0, i))
        if quer("intervalos"):
            for k, w in self.w_int.items():
                w.setValue(int(cfg["intervalos"][k]))
        if quer("farm"):
            for k, w in self.w_farm.items():
                v = cfg["farm"][k]
                if isinstance(w, QCheckBox):
                    w.setChecked(bool(v))
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(max(0, w.findData(v)))
                else:
                    w.setValue(int(v))
        if quer("contas"):
            for wc, a in zip(self.widgets_contas, contas):
                wc["nome"].setText(a["name"] if isinstance(a, dict) else a.name)
                sp = a["sprite"] if isinstance(a, dict) else a.sprite
                wc["sprite"].setValue(sp)
                wc["previa"].setPixmap(_icone(sp))
                wc["hunt"].setText(a["hunt"] if isinstance(a, dict) else a.hunt)
                wc["ativa"].setChecked(a["enabled"] if isinstance(a, dict) else a.enabled)
        if quer("atalhos"):
            for k, w in self.w_atalhos.items():
                w.setKeySequence(QKeySequence(cfg["atalhos"].get(k, config_edit.ATALHO_PADRAO.get(k, ""))))
        if quer("desempenho"):
            self.w_leve.setChecked(bool(cfg["desempenho"]["modo_leve"]))
            self.w_economia.setChecked(bool(cfg["desempenho"]["economia_em_segundo_plano"]))
        if quer("atualizacao"):
            self.w_avisar.setChecked(bool(cfg.get("atualizacao", DEFAULTS["atualizacao"])["avisar"]))

    def _restaurar(self, titulo: str, secao: str):
        if not perguntar(self, "Restaurar padrão", f"Voltar \"{titulo}\" para os valores "
                         f"padrão? (só grava ao clicar em Salvar)"):
            return
        padrao = [{"name": f"Conta {i + 1}", "sprite": DEFAULT_SPRITES[i % len(DEFAULT_SPRITES)], "hunt": "", "enabled": True}
                  for i in range(len(self.accounts))]
        self._carregar(DEFAULTS, padrao, {secao})

    def valores(self) -> tuple[dict, list[dict]]:
        v = {(None, "iniciar_contas_ao_abrir"): self.w_iniciar.isChecked(),
             (None, "max_simultaneas"): self.w_max.value(),
             (None, "quantidade_contas"): self.w_qtd.value(),
             (None, "intervalo_inicio_segundos"): self.w_inicio_intervalo.value(),
             ("janela", "zoom"): round(self.w_zoom.value(), 2),
             ("janela", "layout_ver_todas"): self.w_layout.currentData()}
        for k, w in self.w_int.items():
            v[("intervalos", k)] = w.value()
        for k, w in self.w_farm.items():
            if isinstance(w, QCheckBox):
                valor = w.isChecked()
            elif isinstance(w, QComboBox):
                valor = w.currentData()
            else:
                valor = w.value()
            v[("farm", k)] = valor
        for k, w in self.w_atalhos.items():
            v[("atalhos", k)] = w.keySequence().toString(QKeySequence.PortableText)
        v[("desempenho", "modo_leve")] = self.w_leve.isChecked()
        v[("desempenho", "economia_em_segundo_plano")] = self.w_economia.isChecked()
        for chave, w in self.w_bandeja.items():
            v[("janela", chave)] = w.isChecked()
        v[("atualizacao", "avisar")] = self.w_avisar.isChecked()
        contas = [{"nome": wc["nome"].text().strip(), "sprite": wc["sprite"].value(),
                   "hunt": wc["hunt"].text().strip(), "ativa": wc["ativa"].isChecked()}
                  for wc in self.widgets_contas]
        return v, contas

    def _marcar_erro(self, campo: str | None, msg: str):
        for w in self.campos.values():
            if w.property("erro"):
                w.setProperty("erro", False)
                w.style().unpolish(w)
                w.style().polish(w)
        self.erro.setText(msg)
        w = self.campos.get(campo) if campo else None
        if w is not None:
            w.setProperty("erro", True)
            w.style().unpolish(w)
            w.style().polish(w)
            w.setToolTip(msg)
            self.rolagem.ensureWidgetVisible(w)
            w.setFocus()

    def salvar(self) -> bool:
        valores, contas = self.valores()
        try:
            config_edit.salvar(self.path, valores, contas)
        except ErroConfig as e:
            self._marcar_erro(e.campo, str(e))
            return False
        except OSError as e:
            self._marcar_erro(None, f"não consegui gravar o config.toml: {e}")
            return False
        self._marcar_erro(None, "")
        # o que só vale ao reabrir e mudou em relação ao que está rodando agora
        rod = self.cfg_rodando
        depois = [rot for (sec, k), rot in (((None, "iniciar_contas_ao_abrir"), "iniciar ao abrir"),
                                            ((None, "quantidade_contas"), "contas no programa"),
                                            (("janela", "iniciar_na_bandeja"), "abrir na bandeja"),
                                            (("janela", "zoom"), "zoom inicial"),
                                            (("desempenho", "modo_leve"), "Modo Leve"))
                  if (sec, k) in valores and valores[(sec, k)] != (rod.get(k) if sec is None else rod[sec].get(k))]
        self.salvo.emit(valores, contas)
        if depois:
            avisar(self, "Ajustes salvos",
                                    "Salvo. Reinicie o PokeNexus (feche e abra de novo) para aplicar: "
                                    + ", ".join(depois) + ".")
        self.accept()
        return True
