# PokeNexus — instruções para agentes de IA

Leia isto antes de mexer no projeto. Detalhes de uso estão no `README.md`.

## Idioma

Fale **sempre em português (pt-BR)** com o usuário, inclusive nas mensagens curtas de andamento. O
código, os comentários e os nomes já são em português: mantenha.

## O que é

App desktop para Windows (Python 3.11+, PySide6/Qt WebEngine) que roda até **4 contas** do PokeIdle
(https://pokeidle.io/app) ao mesmo tempo, com o jogo de cada conta embutido na janela.

- `main.py` — entrada. `browser/web_host.py` — uma página Qt WebEngine com perfil próprio por conta.
- `browser/cdp.py` — cliente DevTools de cada página. O app escuta o WebSocket do jogo
  (`game/pokeidle.py`) e o farm **age pelo DOM**, clicando nos botões do próprio jogo. **Exceção, por
  escolha do usuário (16/10/2026): o Mercado** (`rmt/canal.py`) manda pela conexão do jogo os mesmos
  pedidos que o botão manda (`market.item`, `market.comprar`), sem abrir tela: antes cada olhada abria e
  fechava o mercado por cima do jogo e a tela piscava. Um pedido por anúncio, sem rajada.
- `app/manager.py` + `workers/` — loop asyncio numa thread; uma tarefa por conta; vigias de travamento e
  de memória.
- Distribuição: `instalador/PokeNexus.iss` (Inno Setup, por usuário, sem admin, em
  `%LOCALAPPDATA%\Programs\PokeNexus`; `AppId` fixo, **nunca troque**), `instalador/fumaca.ps1` (teste de
  fumaça), `instalador/requirements-build.txt` (versões exatas do build), `.github/workflows/release.yml`
  (publica a Release a cada commit na `main`) e `app/atualizacao.py` (aviso de atualização: faixa no topo,
  escolha do usuário em 16/10/2026; Atualizar baixa, confere o SHA-256, fecha pelo caminho do X e um
  "ajudante" PowerShell roda o instalador depois que o processo termina). Versão: `APP_VERSION_BASE` +
  número do Actions, gravada em `app/_build.py` (não versionado); do código é `1.1-dev`, sem aviso.
- Interface: `app/gui.py` (janela, VER TODAS em grade ou "celulares", painel da conta recolhível),
  `app/widgets.py`, `app/hunt_ui.py` (Hunt Analyzer), `app/rmt_ui.py` + `rmt/` (RMT/Mercado),
  `app/settings_ui.py` + `app/config_edit.py` (Configurações; grava o `config.toml` mantendo os
  comentários).
- Calculadora de Gemas no Mercado (16/10/2026): `app/conversor_gemas.py` (a conta, com `Decimal`, sem Qt;
  teste em `ferramentas/calculadora/teste_conta.py`) + `CalculadoraGemas` em `app/rmt_ui.py` (recolhida no
  cartão do Saldo, botão "Calculadora", escolha do usuário; mascote Meowth Nº 52; falas em
  `app/textos_guia.py` `FRASES_MEOWTH`). **A taxa da calculadora é a de referência do usuário
  (1.000 Gemas = US$ 9,00), num lugar só (`GEMAS_REF`, `CENTAVOS_REF`)**: não use o preço do jogo
  (`welcome.economia`) nem espalhe o número pelo código. Ela só calcula: não compra, não grava, sem rede.
- Pokédex (17/10/2026): `game/pokedex.py` (sem Qt: lista, captura, arquivo `profiles\conta_XX\pokedex.json`;
  teste em `ferramentas/pokedex/teste_dados.py`), `app/pokedex_ui.py` (a tela, visual "aparelho" escolhido pelo
  usuário; `QListView` + delegate, nada de widget por pokémon, sem animação), `game/pokeidle.py` guarda a
  Pokédex do jogo em `self.dex` (só acréscimo), botão no topo no lugar do antigo "N/4 conectadas" e Ctrl+D (o
  padrão fica em `config_edit.ATALHO_PADRAO`). **A Pokédex só lê; a lista de espécies vem dos sprites ∩ catálogo
  do jogo no ar** (nada fixo no código). Pego = Pokédex do jogo `c > 0` + inventário da conta (pedido do usuário)
  + evento `capturado`; Mega/Forma seguem o jogo. A Pokébola das células é `assets/sprites/ui/bola_capturado.png`
  (pacote pokesprite, que o usuário mandou); a Great Ball do botão do topo é `bola_botao.png` e a Ultra Ball
  do cabeçalho é `bola_pokedex.png`. Relatório em `docs/pokedex/RELATORIO.md`.
- `hunts/` — motor do Hunt Analyzer; `hunts/bridge.js` usa os módulos do próprio jogo.
- **Bandeja e fechar (13/11/2026, `docs/bandeja/RELATORIO.md`):** o X (e o Alt+F4) **esconde** na bandeja
  (`app/bandeja.py`), com as contas, o Mercado e os vigias rodando (eles vivem na thread do Manager, não na
  janela). **Fechar de verdade é só pelo `MainWindow.sair()`**: bandeja → Sair, fim de sessão do Windows e o
  Restart Manager do instalador (`commitDataRequest`), atualizador. O `aboutToQuit` é só a rede de segurança.
  `setQuitOnLastWindowClosed(False)`: nada fecha sozinho. Teste que precisa fechar o app: fim de sessão
  (WM_QUERYENDSESSION/WM_ENDSESSION, como `instalador/fumaca.ps1`), não o X. **Uma cópia só por pasta de
  dados** (`app/instancia.py`, mutex + `QLocalServer`): a segunda mostra a janela da primeira e sai antes de
  criar página ou perfil; travada = pergunta se fecha; morta = o Windows solta o mutex.
  `POKENEXUS_DATA` diferente = cópias independentes. Testes em `ferramentas/bandeja/`.
- Modo Leve: só a opção `[desempenho] modo_leve` nas Configurações (vale ao reiniciar). **Não existe**
  mais executável separado "Leve" — o usuário não quer. **Leve 2.0** (`browser/web_host.py`): NÃO
  force `--disable-gpu` (num PC com placa deixava o jogo mais travado, medido). Com placa: GPU +
  "reduzir movimento". Sem placa (`tem_gpu()` pela DXGI): `--disable-gpu` + `QT_QUICK_BACKEND=software`.
  Ferramenta de medição em `ferramentas/desempenho/` (só para teste, não vai no pacote).
- **Visual (tema "Base do Treinador", aprovado pelo usuário):** toda cor, fonte e folha de estilo vem de
  `app/tema.py` (`T[...]`, `qss()`); **nenhuma cor fixa fora dele**. Ícones de pixel em `app/icones.py`
  (nada de emoji em botão); avisos/perguntas por `app/dialogos.py` (`avisar`, `perguntar`), nunca
  `QMessageBox`. A arte (molduras 9-slice, 124 ícones, logo, `.ico`) é própria, gerada por
  `ferramentas/arte/gerar_ui.py` e `gerar_marca.py` em `assets/ui`, `assets/marca`. Fontes Jersey 10
  (só 20/30/40 px, peso 400) e Nunito em `assets/fonts` (OFL). Textos curtos, sem "·" nem "—" na tela.
  A área do jogo não pode encolher (medir com o xadrez azul do jogo nos prints).
  **Desempenho:** as molduras NÃO usam `border-image` no QSS (o Qt recortava e esticava a imagem a
  cada pintura: repintar a janela levava ~8–10 ms). Painéis/fichas usam `Moldura` e todo botão usa
  `Botao` (`app/molduras.py`), que copiam a moldura já montada em memória (~4 ms). O QSS só reserva a
  largura da borda (`tema.moldura`). Botão novo: `Botao(...)`, nunca `QPushButton(...)`; painel novo:
  `Moldura()` com objectName "card". Não chame `setStyleSheet` em todo `refresh()` (refaz o estilo
  mesmo sem mudança).
- **Guias (tutoriais na tela):** `app/guia.py` (`Guia(painel, passos, alvos).abrir()`), textos em
  `app/textos_guia.py` (cada passo com o comentário da linha de código que prova o texto: mudou o
  código, mude o texto). O do Mercado abre pelo botão "Guia" (`RmtPanel.abrir_guia`). O guia só explica:
  não clica nem muda nada, não tem timer nem animação e é apagado ao fechar.
  **O ícone do programa (`assets/pokenexus.ico`) e o logo do topo são a Poké Ball, por escolha do
  usuário** (ele não gostou do mascote "Broto" no lugar). Não trocar sem ele pedir. O `.ico` precisa ter
  16/24/32/48/256 px (`ferramentas/arte/gerar_icone_pokebola.py`); com só 256 px o Windows mostrava o
  ícone velho do cache na pasta e na barra de tarefas. Depois de trocar o ícone:
  `ie4uinit.exe -ClearIconCache`.

## Dados do usuário

- Ficam em `%LOCALAPPDATA%\PokeNexus` (`config.toml`, `profiles\conta_XX` com os logins, `logs\`).
- `POKENEXUS_DATA=<pasta>` troca a pasta de dados. **Use sempre uma pasta temporária nos testes.**
- Nunca leia, copie ou envie tokens/cookies dos perfis. Cópias temporárias com logins têm de ser apagadas
  no fim.
- `profiles/`, `logs/` e saídas de build nunca vão para o Git; confira com a trava antes de todo push.

- **Rede (22/10/2026, `docs/rede/RELATORIO.md`):** o navegador embutido usa DNS seguro com volta para o do
  sistema (`browser/web_host.py` `configurar_dns`, `QWebEngineGlobalSettings.setDnsMode`, antes de qualquer
  perfil); erros de rede são traduzidos só na tela (`app/erros_rede.py`; o código do Chromium vai na dica), o
  log guarda o original. O contador do topo mostra só as contas jogando ("N/4 jogando"); o limite continua
  em `Manager.connected_count`/`can_connect` (contas iniciadas): não mude. O aviso de atualização tenta o
  DNS seguro (1.1.1.1, depois 8.8.8.8) quando o DNS do Windows não acha o GitHub (`atualizacao._abrir`).
  Testes em `ferramentas/rede/` e `ferramentas/atualizacao/teste_doh.py`.

## Regras que não mudam

- **Máximo de 4 contas** (Termos do PokeIdle, seção 5). Nada para burlar anti-bot, limites, travas ou
  regras do jogo, nem para esconder a automação.
- **Contas reais:** nenhum teste conecta as contas reais sem o usuário autorizar. Antes, confira se o
  PokeNexus dele está aberto (`Get-Process PokeNexus`) — a mesma conta aberta em dois lugares derruba a
  sessão dele. Também não use as contas se ele estiver com elas abertas no navegador (Opera).
- **Mercado (RMT):** nenhuma compra real sem autorização do usuário caso a caso (item, preço, quantidade,
  conta). Nunca mexa em Gemas/USDT, carteira, Pix, cartão ou Diamantes. Mercado 2.0: lista de compras
  por conta em `profiles\conta_XX\rmt_compras.json` (`rmt/compras.py`), rotina em `rmt/rotina.py` (uma
  ação por vez, confere antes de cada passo que o item segue ligado e a conta segue caçando). A venda
  automática saiu (as regras de venda antigas ficam guardadas, desligadas). **Compra na liberação**
  (16/10/2026): olha a vitrine a cada `intervalo_s` (60 s; a retenção do jogo é 2 min) e marca UM pedido
  para o instante em que o anúncio libera (sorteio do jogo nos primeiros 3 s). Travas: nunca compra das
  contas próprias, duas contas suas nunca pedem o mesmo anúncio, 3 recusas seguidas desligam o item,
  para com a conta sem conexão ou pausada.
- **Não sobrescreva `dist\`** com o `PokeNexus.exe` do usuário aberto. Gere em outra pasta
  (`--distpath dist_novo`) e troque quando ele fechar.
- **Não diga que funciona sem testar.** Se um teste falhar, ache a causa; não remova a funcionalidade.
- Nas janelas com números e listas, a roda do mouse não pode mudar valores (`widgets.travar_roda`). Já
  aconteceu de "Contas no programa" cair de 4 para 1 sem o usuário ver.

## Rodar, testar e gerar

- Rodar do código: `.venv\Scripts\python.exe main.py`
- Testes de interface com WebEngine precisam de uma janela de verdade (rodam num terminal normal, não em
  sandbox). Use `POKENEXUS_DATA` numa pasta nova: as contas abrem na tela de login e nada das contas reais
  é tocado.
- **Publicar uma versão:** commit na `main` (o Actions faz build, travas, ZIP, instalador, SHA256SUMS e a
  Release). `[sem atualização]` na mensagem, ou commit só em `docs/`, `*.md`, `ferramentas/`: não publica.
  **Nunca token ou senha no programa** (o repositório é público e o aviso consulta sem login); Releases
  só pelo Actions, com as travas. Testes do aviso: `ferramentas/atualizacao/` (servidor falso de
  Releases, builds de teste em `dist_teste\`, automação da janela) e `docs/atualizacao/RELATORIO.md`.
  Instalar a versão de teste na máquina do usuário cria atalhos: ele tem um `PokeNexus.lnk` próprio na
  Área de Trabalho (aponta para outra pasta): guarde e devolva.
- Gerar a versão local: `build.bat` (para no fim esperando uma tecla; gera o instalador se houver Inno
  Setup 6; `set VERSAO_BUILD=1.1.5` antes = build com aviso de atualização). Equivalente direto:
  `.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean PokeNexus.spec`, depois compactar
  `dist\PokeNexus` em `dist\PokeNexus-<versão>.zip`. A pasta tem ~321 MB e o ZIP ~133 MB.
- Se o PyInstaller der "acesso negado" numa DLL de `dist`, algum processo está com ela aberta: gere com
  `--distpath dist_novo` e troque depois.
- Pacote para amigos testarem: `ferramentas\pacote_amigos\montar.ps1` (programa + LEIA-ME + .bat de
  relatório sem logins). Mudou um padrão do `config.toml` (ex.: mascote)? Quem já usou fica com o velho:
  acrescente uma migração em `app/config.py` `_migrar_config` (uma vez só, `migracoes.txt`).
- Testar o ZIP: descompactar numa pasta nova, rodar sem Python no PATH, abrir, fechar no X e conferir
  que não sobra nenhum processo.
- `$env:TEMP` aparece como `PAULOA~1`: resolva o caminho longo antes de comparar com caminhos de
  processos.

## Próximos passos (prompts na raiz)

1. `PROMPT_IDENTIDADE_VISUAL.md` — **feito** (15/10/2026, direção A). Relatório em
   `docs/visual/V6_RELATORIO.md`. **Os sprites de Pokémon (`assets/sprites/pokemon`) ficam**: o usuário
   quer os Pokémon originais como mascotes e não quer criaturas inventadas. Não troque nem remova.
2. `PROMPT_GUIA_MERCADO.md` — guia do Mercado (`app/guia.py`, `app/textos_guia.py`) já existe.
   `PROMPT_MERCADO_V2.md` — **feito no código** (15/10/2026): lista de compras, Ligado/Desligado por
   item, limites opcionais, guia novo, migração das regras antigas; testes offscreen e prints em
   `docs/visual/mercado2`. **Falta:** a prova com compra real pequena (só com autorização do usuário) e
   conferir que o farm não piora com o Mercado ligado.
3. `PROMPT_MODO_LEVE_V2.md` — **feito (15/10/2026), versão enxuta a pedido do usuário** (ele mandou parar os testes longos). Medido sem contas reais: P1 e P3. Faltou: as 3 rodadas completas, P2, Modo Economia (A8) e o farm com contas reais. Resultados em `docs/desempenho/HIPOTESES.md`.
4. `PROMPT_ASSINATURA_PREMIUM.md` — assinatura de R$ 5 por Pix, site com conta e confirmação de e-mail,
   app só para assinantes. Começa pela Etapa 0 (decisões do usuário: nome sem "Poke", autorização do
   PokeIdle, provedor de Pix, taxas, contador e advogado).
5. `PROMPT_GITHUB_E_LIMPEZA.md` — **parcialmente feito** (16/10/2026): o usuário apagou e recriou o
   repositório, e o histórico limpo (1 commit, sem `profiles/`, `logs/` nem builds; trava conferida num
   clone) foi enviado como `main`. A branch local `antiga-com-logins` guarda o histórico velho: **nunca envie**
   (sem `git push --all`). **Falta** a limpeza do código não usado, **sem mudar nada do app**. Os
   `PROMPT_*.md` antigos ficam só na pasta local, em `docs/prompts_antigos/` (fora do Git, escolha do usuário).
6. Vistoria da interface após o PokeIdle 1.300.2 — **feita** (16/10/2026). Relatório em
   `docs/visual/interface_1300/RELATORIO.md`. O Market cortado é defeito do jogo (altura fixa desde
   15/10/2026); por escolha do usuário o PokeNexus baixa o zoom só enquanto o Market do jogo está aberto
   (`CellsHost.MARKET_CSS_H`, só lê a página). Ferramentas de teste em `ferramentas/interface/` (não vão
   no pacote). Pendentes no relatório (Ginásios com o mesmo defeito do jogo, itens Baixa de janela estreita).
7. Instalador + aviso de atualização — **feito no código e testado na máquina** (16/10/2026), relatório
   em `docs/atualizacao/RELATORIO.md`. Falta a primeira publicação de verdade no GitHub (teste 8, com o
   OK do usuário).

8. Calculadora Gemas ⇄ Dólares no Mercado — **feita e testada** (16/10/2026), relatório em
   `docs/visual/calculadora/RELATORIO.md`. Publicada na v1.1.5.
9. Pokédex — **feita e testada sem contas reais** (17/10/2026), relatório em `docs/pokedex/RELATORIO.md`. Falta: a
   conferência com uma conta real e o farm de 4 contas (só com autorização) e o push (publica atualização).
10. Identidade Artística 2.0: abandonada em 22/10/2026; guardada em
   `C:\Users\Paulo Afonso\Documents\PokeNexus_arquivo\identidade2_20261022-0957.zip` (+ `identidade2.patch` na
   mesma pasta) e no stash `Identidade 2.0 abandonada (20/10/2026)` (`git stash list`). Não volte a ela sem o
   usuário pedir.

Prompts antigos já executados: `PROMPT_CONFIG_MODO_LEVE.md`, `PROMPT_RMT_VERTICAL.md`.
