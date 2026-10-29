"""Caminhos do PokeNexus e leitura do config.toml (com valores padrão para tudo que faltar).

Arquivos do programa (código, sprites, config padrão) ficam junto do executável.
Dados do usuário (config.toml, perfis com login, logs) ficam em %LOCALAPPDATA%\\PokeNexus:
assim, repassar a pasta do programa nunca leva os logins junto, e atualizar o programa
não apaga nada.
"""
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "PokeNexus"
# MAJOR.MINOR. O terceiro número é o da execução do GitHub Actions, gravado no app/_build.py só no
# build de publicação (ver .github/workflows/release.yml). Rodando do código: "1.1-dev", e o aviso de
# atualização fica desligado.
APP_VERSION_BASE = "1.1"
try:
    from app._build import COMMIT as APP_COMMIT, VERSAO as APP_VERSION
    VERSAO_DE_BUILD = True
except ImportError:
    APP_VERSION, APP_COMMIT, VERSAO_DE_BUILD = f"{APP_VERSION_BASE}-dev", "", False

ROOT = Path(__file__).resolve().parent.parent          # código-fonte
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT))       # arquivos empacotados no .exe
ASSETS_DIR = BUNDLE_DIR / "assets"
SPRITES_POKEMON = ASSETS_DIR / "sprites" / "pokemon"
DEFAULT_CONFIG = BUNDLE_DIR / "config.toml"

# POKENEXUS_DATA troca a pasta de dados (útil para testes; nada é migrado para ela).
CUSTOM_DATA_DIR = bool(os.environ.get("POKENEXUS_DATA"))
DATA_DIR = Path(os.environ.get("POKENEXUS_DATA")
                or Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME)
CONFIG_PATH = DATA_DIR / "config.toml"
PROFILES_DIR = DATA_DIR / "profiles"
LOGS_DIR = DATA_DIR / "logs"

# Limite atual mantido; expansão de contas ficou para uma próxima etapa.
LIMITE_TERMOS = 4
MAX_CONTAS = 4

DEFAULTS = {
    "url": "https://pokeidle.io/app",
    "quantidade_contas": 4,
    "max_simultaneas": 4,
    "iniciar_contas_ao_abrir": True,
    "intervalo_inicio_segundos": 3,
    "intervalos": {
        "verificacao_segundos": 3,
        "sem_resposta_recarregar_segundos": 60,
        "sem_batalha_recarregar_segundos": 180,
        "espera_volta_automatica_segundos": 20,
    },
    "farm": {
        "voltar_apos_derrota": True,
        "max_derrotas": 3,
        "janela_derrotas_minutos": 15,
        "log_cada_batalha": True,
        "reabrir_navegador": True,
        "limite_memoria_pagina_mb": 2000,
        "avancar_melhor_hunt": True,
        "objetivo_hunt": "xp_pokemon",
        "risco_maximo_hunt": "medio",
        "usar_medicoes_reais": True,
        "reavaliar_hunt_minutos": 15,
        "ganho_minimo_troca_pct": 5,
    },
    "janela": {"zoom": 1.0, "layout_ver_todas": "grade", "painel_conta": True, "guia_mercado_visto": False,
               "fechar_para_bandeja": True, "minimizar_para_bandeja": True, "iniciar_na_bandeja": False},
    "desempenho": {"modo_leve": False, "economia_em_segundo_plano": True},
    "atualizacao": {"avisar": True, "versao_pulada": ""},
    "atalhos": {
        "conta_1": "Ctrl+1", "conta_2": "Ctrl+2", "conta_3": "Ctrl+3",
        "conta_4": "Ctrl+4", "ver_todas": "Ctrl+0", "hunts": "Ctrl+H",
        "pausar_retomar": "F8", "configuracoes": "Ctrl+,", "rmt": "Ctrl+M", "painel_conta": "Ctrl+B",
    },
}

def modo_leve() -> bool:
    """O liga/desliga do Modo Leve (⚙ Configurações → Desempenho). Lido ANTES de tudo: as opções do
    navegador valem desde a abertura, por isso a troca só vale ao reabrir o programa."""
    try:
        raw = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        return bool((raw.get("desempenho") or {}).get("modo_leve", False))
    except Exception:
        return False


MODO_LEVE = modo_leve()

DEFAULT_SPRITES = [25, 1, 4, 258]


@dataclass
class Account:
    index: int          # posição na lista, começando em zero
    name: str
    folder: str
    sprite: int
    hunt: str
    enabled: bool

    @property
    def profile_dir(self) -> Path:
        return PROFILES_DIR / self.folder


def prepare_data_dir():
    """Cria a pasta de dados na primeira execução.

    Se o programa já rodava a partir do código-fonte (pastas profiles/ e config.toml ao lado
    do código), copia os perfis e a configuração para cá - os logins continuam valendo.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    antigo = ROOT / "profiles"
    if (not CUSTOM_DATA_DIR and not PROFILES_DIR.exists() and antigo.is_dir()
            and antigo.resolve() != PROFILES_DIR.resolve()):
        for conta in antigo.iterdir():
            if not conta.is_dir():
                continue
            destino = PROFILES_DIR / conta.name
            destino.mkdir(parents=True, exist_ok=True)
            if (conta / "web").is_dir():
                shutil.copytree(conta / "web", destino / "web", dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("cache", "*.lock", "LOCK", "lockfile"))
            if (conta / "manager_state.json").is_file():
                shutil.copy2(conta / "manager_state.json", destino)
        if (ROOT / "config.toml").is_file() and not CONFIG_PATH.exists():
            shutil.copy2(ROOT / "config.toml", CONFIG_PATH)
    PROFILES_DIR.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists() and DEFAULT_CONFIG.is_file():
        shutil.copy2(DEFAULT_CONFIG, CONFIG_PATH)
    _migrar_config()


MIGRACOES = DATA_DIR / "migracoes.txt"      # o que já foi atualizado nesta pasta de dados (uma vez só)


def _migrar_config():
    """Atualiza, UMA vez, o que mudou no padrão de versões antigas. O config.toml da pasta de dados
    nunca é trocado ao instalar uma versão nova, então quem já tinha usado o PokeNexus ficava com o
    padrão velho. Hoje: o mascote da Conta 4 era o Squirtle (7) e passou a ser o Mudkip (258). Quem
    escolher o Squirtle depois disso continua com ele."""
    feitas = set(MIGRACOES.read_text(encoding="utf-8").split()) if MIGRACOES.exists() else set()
    novas = set()
    if "mascote_conta4" not in feitas:
        try:
            texto = CONFIG_PATH.read_text(encoding="utf-8-sig")
            contas = tomllib.loads(texto).get("contas") or []
            if len(contas) >= 4 and int(contas[3].get("sprite") or 0) == 7:
                from app.config_edit import aplicar_no_texto
                novo = aplicar_no_texto(texto, {}, [{}, {}, {}, {"sprite": DEFAULT_SPRITES[3]}])
                if (tomllib.loads(novo).get("contas") or [{}] * 4)[3].get("sprite") == DEFAULT_SPRITES[3]:
                    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
                    tmp.write_text(novo, encoding="utf-8")
                    tmp.replace(CONFIG_PATH)
            novas.add("mascote_conta4")
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            return                   # config com erro: o load_config avisa; tenta de novo na próxima
    # Migração explícita pedida em 28/10/2026: instalações antigas também passam a iniciar as contas.
    # A pessoa ainda pode desligar depois em Ajustes; a marca impede sobrescrever essa escolha.
    if "inicio_automatico_20261028" not in feitas:
        try:
            from app.config_edit import aplicar_no_texto
            texto = CONFIG_PATH.read_text(encoding="utf-8-sig")
            novo = aplicar_no_texto(texto, {None: {"iniciar_contas_ao_abrir": True,
                                                   "intervalo_inicio_segundos": 3}}, [])
            tomllib.loads(novo)
            tmp = CONFIG_PATH.with_suffix(".toml.tmp")
            tmp.write_text(novo, encoding="utf-8")
            tmp.replace(CONFIG_PATH)
            novas.add("inicio_automatico_20261028")
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            return
    try:
        MIGRACOES.write_text("\n".join(sorted(feitas | novas)) + "\n", encoding="utf-8")
    except OSError:
        pass


def _merge(base: dict, extra: dict) -> dict:
    out = {k: _merge(v, {}) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in extra.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_config(path: Path = CONFIG_PATH) -> tuple[dict, list[Account]]:
    raw = {}
    if path.exists():
        # utf-8-sig: aceita o arquivo salvo como "UTF-8 com BOM" (opção do Bloco de Notas).
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    cfg = _merge(DEFAULTS, {k: v for k, v in raw.items() if k != "contas"})
    for chave in ("quantidade_contas", "max_simultaneas", "intervalo_inicio_segundos"):
        valor = cfg[chave]
        minimo = 0 if chave == "intervalo_inicio_segundos" else 1
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
            raise ValueError(f"{chave} precisa ser um inteiro maior ou igual a {minimo}.")
    cfg["max_simultaneas"] = min(cfg["max_simultaneas"], LIMITE_TERMOS)
    cfg["quantidade_contas"] = qtd = min(cfg["quantidade_contas"], MAX_CONTAS)
    listed = raw.get("contas", [])
    accounts = []
    for i in range(qtd):
        a = listed[i] if i < len(listed) else {}
        accounts.append(Account(
            index=i,
            name=str(a.get("nome") or f"Conta {i + 1}"),
            folder=str(a.get("pasta") or f"conta_{i + 1:02d}"),
            sprite=int(a.get("sprite") or DEFAULT_SPRITES[i % len(DEFAULT_SPRITES)]),
            hunt=str(a.get("hunt") or "").strip(),
            enabled=bool(a.get("ativa", True)),
        ))
    folders = [a.folder for a in accounts]
    if any(Path(p).name != p or p in (".", "..") or ":" in p or "\\" in p or "/" in p for p in folders):
        raise ValueError("Cada 'pasta' precisa ser um nome simples dentro de profiles.")
    if len({p.casefold() for p in folders}) != len(folders):
        raise ValueError("Duas contas usam a mesma 'pasta' no config.toml - cada conta precisa da sua.")
    return cfg, accounts
