"""Seletores do DOM do PokeIdle (https://pokeidle.io/app).

Todos são IDs/atributos fixos do próprio jogo, encontrados lendo o app.js
(versão 1.279.2). Se o jogo mudar e algo parar de funcionar, é aqui que se ajusta.
"""

# --- Telas (visíveis = sem a classe "hidden") -------------------------------
TELA_CARREGANDO = "carregando"          # barra de carregamento inicial
TELA_LOGIN = "login"                    # tela de login => sessão não existe/expirou
TELA_APP = "app"                        # o jogo em si
SESSAO_TOMADA = "sessao-tomada"         # "Conta aberta em outro lugar"
ALERTA_CONTA = "alerta-conta"           # ban, rede cheia, sessão inválida...
ALERTA_CONTA_TEXTO = "alerta-conta-texto"
ALERTA_CONTA_MOTIVO = "alerta-conta-motivo"
TERMOS_ACEITE = "termos-aceite"         # termos novos para aceitar (manual!)
ONBOARDING = "onboarding"               # criação do personagem
STARTER = "starter"                     # escolha do pokémon inicial
ESCOLHER_NICK = "escolher-nick"
CONFIRMAR_EMAIL = "confirmar-email"
AVISO_VERSAO = "aviso-versao"           # "nova versão do jogo"

# Telas que exigem uma pessoa (o programa nunca clica nelas).
TELAS_MANUAIS = {
    TERMOS_ACEITE: "aceite os Termos novos do jogo",
    ONBOARDING: "termine a criação do personagem",
    STARTER: "escolha o pokémon inicial",
    ESCOLHER_NICK: "escolha um nick",
    CONFIRMAR_EMAIL: "confirme o e-mail da conta",
}

# --- Botões -----------------------------------------------------------------
BTN_RECARREGAR_VERSAO = "#aviso-versao-btn"
BTN_CURAR_CENTRO = "#centro-curar"      # Centro Pokémon (cena normal)
BTN_CURAR_ECO = "#eco-curar"            # Centro Pokémon (Modo Economia)
BTN_MAPA = 'button[data-modal="mapa"]'  # menu "Mapa"
MARCADOR_HUNT = 'button.marcador[data-slug="{slug}"]'  # área no mapa
MAPA_REGIAO = '.mapa-area[data-regiao="{regiao}"]'     # botão da região no Mapa (uma tela por região)
MAPA_REGIAO_QUALQUER = '.mapa-area[data-regiao]'       # o Mapa está aberto
# As regiões do Mapa que dá para abrir (as travadas por nível ficam de fora).
JS_REGIOES_DO_MAPA = """() => [...document.querySelectorAll('.mapa-area[data-regiao]')]
  .filter((b) => !b.disabled && !b.classList.contains('mapa-area-travada')).map((b) => b.dataset.regiao)"""

# Clica no marcador da área SÓ se a trava de combate do jogo estiver livre. Quem diz é o próprio
# botão "Ir para o Centro" (#ir-centro, ou o do Modo Economia), que o jogo liga/desliga 12×/s com a
# mesma regra do servidor: 3 s sem trocar dano, ou livre entre ondas / antes do 1º golpe da onda.
JS_CLICAR_SE_LIVRE = """(sel) => {
  const centro = document.querySelector('#hunt-saida:not(.hidden) #ir-centro')
    || document.querySelector('#eco-ir-centro:not(.hidden)');
  if (centro && centro.disabled) return 'travado';
  const m = document.querySelector(sel);
  if (!m) return 'sem marcador';
  m.click();
  // No layout de CELULAR do jogo o toque no marcador só abre a ficha da área; quem entra na hunt é o
  // botão "Caçar" dela (que passa pela mesma trava do jogo).
  if (document.documentElement.classList.contains('mobile')) {
    const cacar = document.querySelector('.ha-cacar');
    if (!cacar) return 'ficha';
    if (cacar.disabled || cacar.classList.contains('travada')) return 'travado';
    cacar.click();
  }
  return 'ok';
}"""
BTN_FECHAR_MODAL = "#modal-fechar"

# --- Painel do treinador (só leitura) ---------------------------------------
TR_NICK = "tr-nick"
TR_LEVEL = "tr-level"
TR_XP = "tr-xp-txt"

# Avalia, numa chamada só, o que está na tela.
JS_LER_TELA = """() => {
  const el = (id) => document.getElementById(id);
  const vis = (id) => { const e = el(id); return !!e && !e.closest('.hidden')
      && getComputedStyle(e).display !== 'none'; };
  const txt = (id) => (el(id)?.textContent ?? '').trim();
  const ids = %s;
  const out = {};
  for (const id of ids) out[id] = vis(id);
  out.alerta_texto = (txt('alerta-conta-titulo') + ' - ' + txt('alerta-conta-texto') + ' ' + txt('alerta-conta-motivo')).trim();
  out.nick = txt('tr-nick');
  out.level = txt('tr-level');
  out.xp = txt('tr-xp-txt');
  return out;
}""" % repr([TELA_CARREGANDO, TELA_LOGIN, TELA_APP, SESSAO_TOMADA, ALERTA_CONTA,
             TERMOS_ACEITE, ONBOARDING, STARTER, ESCOLHER_NICK, CONFIRMAR_EMAIL, AVISO_VERSAO])
