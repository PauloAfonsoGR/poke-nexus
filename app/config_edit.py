"""Validação e gravação das Configurações no config.toml SEM regerar o arquivo.

Só as linhas `chave = valor` que mudaram são trocadas (o comentário do fim da linha fica); chaves
que faltam entram no fim da seção delas; seções que faltam entram antes das contas. Comentários,
ordem e linhas em branco do arquivo continuam como estavam. No fim o arquivo é lido de volta e
conferido: se algo não bater, nada é gravado.
"""
import json
import re
import tomllib
from pathlib import Path

from PySide6.QtGui import QKeySequence

from app.config import LIMITE_TERMOS, MAX_CONTAS, SPRITES_POKEMON

# (seção, chave): (tipo, mínimo, máximo, vale_na_hora)
CAMPOS = {
    (None, "quantidade_contas"): (int, 1, MAX_CONTAS, False),
    (None, "max_simultaneas"): (int, 1, LIMITE_TERMOS, True),
    (None, "iniciar_contas_ao_abrir"): (bool, None, None, False),
    (None, "intervalo_inicio_segundos"): (int, 0, 300, True),
    ("intervalos", "verificacao_segundos"): (int, 1, 60, True),
    ("intervalos", "sem_resposta_recarregar_segundos"): (int, 15, 3600, True),
    ("intervalos", "sem_batalha_recarregar_segundos"): (int, 30, 7200, True),
    ("intervalos", "espera_volta_automatica_segundos"): (int, 0, 600, True),
    ("farm", "voltar_apos_derrota"): (bool, None, None, True),
    ("farm", "max_derrotas"): (int, 1, 50, True),
    ("farm", "janela_derrotas_minutos"): (int, 1, 240, True),
    ("farm", "log_cada_batalha"): (bool, None, None, True),
    ("farm", "reabrir_navegador"): (bool, None, None, True),
    ("farm", "limite_memoria_pagina_mb"): (int, 0, 16000, True),
    ("farm", "avancar_melhor_hunt"): (bool, None, None, True),
    ("farm", "objetivo_hunt"): (str, ("xp_pokemon", "xp_treinador", "ouro"), None, True),
    ("farm", "risco_maximo_hunt"): (str, ("baixo", "medio"), None, True),
    ("farm", "usar_medicoes_reais"): (bool, None, None, True),
    ("farm", "reavaliar_hunt_minutos"): (int, 5, 240, True),
    ("farm", "ganho_minimo_troca_pct"): (int, 1, 100, True),
    ("janela", "zoom"): (float, 0.5, 2.0, False),
    ("janela", "layout_ver_todas"): (str, ("grade", "celulares"), None, True),
    ("janela", "painel_conta"): (bool, None, None, True),
    ("janela", "guia_mercado_visto"): (bool, None, None, True),
    ("janela", "fechar_para_bandeja"): (bool, None, None, True),
    ("janela", "minimizar_para_bandeja"): (bool, None, None, True),
    ("janela", "iniciar_na_bandeja"): (bool, None, None, False),
    ("desempenho", "modo_leve"): (bool, None, None, False),
    ("desempenho", "economia_em_segundo_plano"): (bool, None, None, True),
    ("atualizacao", "avisar"): (bool, None, None, True),
}
ATALHOS = ("conta_1", "conta_2", "conta_3", "conta_4", "ver_todas", "hunts", "rmt", "pokedex", "pausar_retomar",
           "configuracoes", "painel_conta")
NOMES_ATALHOS = {"conta_1": "Conta 1", "conta_2": "Conta 2", "conta_3": "Conta 3", "conta_4": "Conta 4",
                 "ver_todas": "Todas as contas", "hunts": "Jogo / Hunts", "rmt": "Jogo / Mercado",
                 "pokedex": "Jogo / Pokédex", "pausar_retomar": "Pausar / retomar",
                 "configuracoes": "Ajustes", "painel_conta": "Mostrar / esconder a ficha do treinador"}
# Atalhos novos que ainda não estão nos padrões do app/config.py: valem quando o config.toml não tem a chave.
ATALHO_PADRAO = {"pokedex": "Ctrl+D"}
CAMPOS_CONTA = ("nome", "sprite", "hunt", "ativa")


class ErroConfig(ValueError):
    """Valor recusado: `campo` diz onde mostrar a mensagem na tela."""

    def __init__(self, campo: str, msg: str):
        super().__init__(msg)
        self.campo = campo


# ------------------------------------------------------------------ validação
def validar(valores: dict, contas: list[dict]) -> None:
    """valores: {(seção, chave): valor} + {("atalhos", nome): "Ctrl+1"}; contas: [{nome, sprite,
    hunt, ativa}]. Levanta ErroConfig no primeiro valor inválido."""
    for (sec, k), v in valores.items():
        nome = f"{sec}.{k}" if sec else k
        if sec == "atalhos":
            if v and QKeySequence(v).isEmpty():
                raise ErroConfig(nome, f"atalho inválido: {v!r}")
            continue
        tipo, mn, mx, _ = CAMPOS[(sec, k)]
        if tipo is str:
            if v not in mn:
                raise ErroConfig(nome, "opção inválida: " + " ou ".join(mn))
            continue
        if tipo is bool:
            if not isinstance(v, bool):
                raise ErroConfig(nome, "precisa ser sim ou não")
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ErroConfig(nome, "precisa ser um número")
        if tipo is int and int(v) != v:
            raise ErroConfig(nome, "precisa ser um número inteiro")
        if k == "limite_memoria_pagina_mb" and 0 < v < 500:
            raise ErroConfig(nome, "use 0 (desligado) ou pelo menos 500 MB")
        if mx is None and v < mn:
            raise ErroConfig(nome, f"precisa ser pelo menos {mn}")
        if mx is not None and not mn <= v <= mx:
            raise ErroConfig(nome, f"precisa estar entre {mn} e {mx}")
    usados = {}
    for k in ATALHOS:
        v = valores.get(("atalhos", k))
        if v:
            chave = QKeySequence(v).toString()
            if chave in usados:
                raise ErroConfig(f"atalhos.{k}", f"o atalho {v} já é usado em \"{NOMES_ATALHOS[usados[chave]]}\"")
            usados[chave] = k
    for i, c in enumerate(contas):
        nome = str(c.get("nome", "")).strip()
        if not 1 <= len(nome) <= 30:
            raise ErroConfig(f"contas.{i}.nome", "o nome precisa ter de 1 a 30 caracteres")
        if any(o["nome"].strip() == nome for o in contas[:i]):
            raise ErroConfig(f"contas.{i}.nome", "duas contas não podem ter o mesmo nome")
        s = c.get("sprite")
        if not isinstance(s, int) or isinstance(s, bool) or not (SPRITES_POKEMON / f"{s}.gif").is_file():
            raise ErroConfig(f"contas.{i}.sprite", "não existe sprite com esse número (1 a 386)")
        if not re.fullmatch(r"[a-z0-9_]*", c.get("hunt", "")):
            raise ErroConfig(f"contas.{i}.hunt", "código da hunt: só letras minúsculas, números e _")
        if not isinstance(c.get("ativa"), bool):
            raise ErroConfig(f"contas.{i}.ativa", "precisa ser sim ou não")


# ------------------------------------------------------------------ gravação
def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(round(v, 4))
    if isinstance(v, int):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


_CHAVE = re.compile(r"^(\s*)([A-Za-z_][\w-]*)(\s*=\s*)(.*)$")


def _separa_valor(resto: str) -> tuple[str, str]:
    """'"Ctrl+1"   # comentário' -> ('"Ctrl+1"', '   # comentário')."""
    if resto.startswith('"'):
        i = 1
        while i < len(resto):
            if resto[i] == "\\":
                i += 2
                continue
            if resto[i] == '"':
                break
            i += 1
        return resto[:i + 1], resto[i + 1:]
    j = resto.find("#")
    if j < 0:
        return resto.rstrip(), resto[len(resto.rstrip()):]
    valor = resto[:j].rstrip()
    return valor, resto[len(valor):]


def aplicar_no_texto(texto: str, secoes: dict, contas: list[dict]) -> str:
    """secoes: {seção ou None: {chave: valor}}; contas: [{chave: valor}] por ordem."""
    linhas = texto.splitlines()
    faltam = {s: dict(v) for s, v in secoes.items()}
    faltam_contas = [dict(c) for c in contas]
    atual = None                    # nome da seção, ou ("contas", n)
    n_contas = -1
    fim_secao = {}                  # seção -> índice da última linha "chave = valor" dela
    inicio_contas = None
    for i, linha in enumerate(linhas):
        tira = linha.strip()
        if tira.startswith("[[") and tira.rstrip().endswith("]]"):
            n_contas += 1
            atual = ("contas", n_contas)
            if inicio_contas is None:
                inicio_contas = i
            fim_secao[atual] = i
            continue
        if tira.startswith("[") and tira.endswith("]"):
            atual = tira[1:-1].strip()
            fim_secao[atual] = i
            continue
        m = _CHAVE.match(linha)
        if not m:
            continue
        fim_secao[atual] = i
        k = m.group(2)
        if isinstance(atual, tuple):
            alvo = faltam_contas[atual[1]] if atual[1] < len(faltam_contas) else {}
        else:
            alvo = faltam.get(atual, {})
        if k in alvo:
            _velho, sobra = _separa_valor(m.group(4))
            linhas[i] = f"{m.group(1)}{k}{m.group(3)}{_toml(alvo.pop(k))}{sobra}"
    # chaves que faltam: no fim da seção delas (de baixo para cima, para os índices valerem)
    insercoes = []
    for sec, resto in faltam.items():
        if resto and sec in fim_secao:
            insercoes.append((fim_secao[sec] + 1, [f"{k} = {_toml(v)}" for k, v in resto.items()]))
            resto.clear()
    for n, resto in enumerate(faltam_contas):
        if resto and ("contas", n) in fim_secao:
            insercoes.append((fim_secao[("contas", n)] + 1, [f"{k} = {_toml(v)}" for k, v in resto.items()]))
            resto.clear()
    for pos, novas in sorted(insercoes, key=lambda x: -x[0]):
        linhas[pos:pos] = novas
    # seções inteiras que faltam: antes do bloco de comentários das contas (ou no fim)
    novas_secoes = []
    for sec, resto in faltam.items():
        if not resto:
            continue
        if sec is None:
            novas_secoes = [f"{k} = {_toml(v)}" for k, v in resto.items()] + [""] + novas_secoes
        else:
            novas_secoes += [f"[{sec}]"] + [f"{k} = {_toml(v)}" for k, v in resto.items()] + [""]
    if novas_secoes:
        inicio = len(linhas)
        for i, linha in enumerate(linhas):
            if linha.strip().startswith("[[contas]]"):
                inicio = i
                while inicio > 0 and (linhas[inicio - 1].strip().startswith("#") or not linhas[inicio - 1].strip()):
                    inicio -= 1
                break
        linhas[inicio:inicio] = ([""] if inicio and linhas[inicio - 1].strip() else []) + novas_secoes
    # contas que não existem no arquivo: blocos novos no fim
    for n, resto in enumerate(faltam_contas):
        if resto:
            linhas += ["", "[[contas]]"] + [f"{k} = {_toml(v)}" for k, v in resto.items()]
    return "\n".join(linhas) + "\n"


def salvar_um(path: Path, sec, chave: str, valor) -> None:
    """Grava UMA opção (ex.: o layout do VER TODAS escolhido na tela), mantendo o arquivo."""
    if (sec, chave) in CAMPOS:
        validar({(sec, chave): valor}, [])
    texto = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    novo = aplicar_no_texto(texto, {sec: {chave: valor}}, [])
    lido = tomllib.loads(novo)
    if (lido if sec is None else lido.get(sec, {})).get(chave) != valor:
        raise ErroConfig(chave, f"não consegui gravar {chave}")
    if novo != texto:
        tmp = path.with_suffix(".toml.tmp")
        tmp.write_text(novo, encoding="utf-8")
        tmp.replace(path)


def salvar(path: Path, valores: dict, contas: list[dict]) -> None:
    """Valida, grava só o que mudou e confere lendo de volta. valores: {(seção, chave): valor}."""
    validar(valores, contas)
    texto = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    secoes: dict = {}
    for (sec, k), v in valores.items():
        secoes.setdefault(sec, {})[k] = v
    novo = aplicar_no_texto(texto, secoes, [{k: c[k] for k in CAMPOS_CONTA if k in c} for c in contas])
    lido = tomllib.loads(novo)                      # erro de sintaxe aqui = não grava nada
    for (sec, k), v in valores.items():
        got = (lido if sec is None else lido.get(sec, {})).get(k)
        if got != v:
            raise ErroConfig(f"{sec}.{k}" if sec else k, f"não consegui gravar {k} (lido de volta: {got!r})")
    lidas = lido.get("contas") or []
    for i, c in enumerate(contas):
        got = lidas[i] if i < len(lidas) else {}
        for k in CAMPOS_CONTA:
            if k in c and got.get(k) != c[k]:
                raise ErroConfig(f"contas.{i}.{k}", f"não consegui gravar {k} da conta {i + 1}")
    if novo != texto:
        tmp = path.with_suffix(".toml.tmp")
        tmp.write_text(novo, encoding="utf-8")
        if path.exists():
            path.with_suffix(".toml.bak").write_bytes(path.read_bytes())
        tmp.replace(path)
