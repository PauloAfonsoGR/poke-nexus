# PokeNexus

Programa para deixar várias contas do [PokeIdle](https://pokeidle.io/app) farmando XP **ao mesmo
tempo**, com o jogo de cada conta **dentro do próprio programa** — uma conta por vez ou todas juntas
na tela (**Todas as contas**) — e assumir o controle de qualquer uma delas quando quiser.

---

## ⚠️ Antes de tudo: o que as regras do PokeIdle permitem

Os [Termos de Uso do PokeIdle](https://pokeidle.io/terms) (seção 5) dizem:

- **Automação é permitida**, desde que siga as mesmas regras de quem joga na mão: sem explorar
  falhas, sem burlar limites do jogo e sem sobrecarregar o servidor.
- **Multicontas:** cada rede pode ter **no máximo 4 contas criadas e 4 contas conectadas ao mesmo
  tempo**, e **mais de 4 contas no mesmo aparelho** são tratadas como multiconta (as contas extras
  podem ser banidas).

Por isso o PokeNexus:

- trabalha com **no máximo 4 contas** (Conta 1 a Conta 4), todas podendo farmar ao mesmo tempo;
- não tem nenhum truque para esconder a automação ou enganar o anti-bot;
- deixa você fazer o login à mão (o "Confirme que é humano" da Cloudflare é feito por você).

---

## 1. Instalar e abrir

1. Abra as **[Releases](https://github.com/PauloAfonsoGR/poke-nexus/releases/latest)** e baixe o
   **`PokeNexus-Setup-<versão>.exe`**.
2. Dê **dois cliques** nele. Não pede administrador: o programa vai para
   `%LOCALAPPDATA%\Programs\PokeNexus`, com atalho no Menu Iniciar e na Área de Trabalho.
3. No fim, "Abrir o PokeNexus" já vem marcado.

Não precisa de Python, navegador nem nada mais. Para desinstalar: **Configurações do Windows → Apps**
(os logins e a configuração ficam; ver abaixo).

> O instalador e o programa não são assinados digitalmente: o Windows pode mostrar "O Windows protegeu o
> computador". Clique em **Mais informações → Executar assim mesmo**.

**Alternativa sem instalar (ZIP):** baixe o `PokeNexus-<versão>.zip` da mesma Release, clique com o botão
direito → **Extrair tudo…** e dê dois cliques em `PokeNexus\PokeNexus.exe`. O ZIP não se atualiza sozinho:
para receber o aviso de atualização, use o instalador.

> **Quem tem a versão 1.1.0 (em ZIP):** ela não tem o aviso de atualização. Instale **uma vez** pelo
> `PokeNexus-Setup`; os logins e a configuração continuam (ficam em outra pasta). Depois, pode apagar a
> pasta do ZIP antigo.

### Atualizações

O PokeNexus instalado procura uma versão nova no GitHub ao abrir (depois de 30 s) e a cada 6 horas. Se
houver, aparece uma faixa no topo: **"Nova versão … disponível"**, com o que mudou e os botões:
- **Atualizar:** baixa o instalador da Release (só do GitHub), confere o SHA-256, fecha o PokeNexus do
  jeito normal (as contas param com segurança; se houver conta conectada, ele pergunta antes), instala e
  abre a versão nova sozinho. Os logins, a configuração e os logs não mudam.
- **Depois:** esconde o aviso até a próxima procura.
- **Pular esta versão:** não avisa mais desta versão (a próxima volta a avisar).

Nada é baixado ou instalado sem o seu clique. Sem internet, nada aparece (só uma linha no log). Em
**Ajustes → Atualização**: "Avisar quando tiver atualização" (ligado por padrão) e **Procurar atualização
agora**.

### Onde ficam os seus dados

Configuração, perfis (com os logins) e logs ficam em **`%LOCALAPPDATA%\PokeNexus`** — fora da pasta
do programa. Assim:
- atualizar, reinstalar ou desinstalar o PokeNexus não apaga os logins;
- se você passar a pasta do programa para alguém, **os seus logins não vão junto**.

Ela abre em **Ajustes → Pastas** (junto com a pasta dos perfis e a de logs).

## 2. Ajustes

O botão **Ajustes** no topo (ou **Ctrl+,**) abre todas as opções do programa numa janela. Abrir
e mexer nela **não para nem recarrega nenhuma conta**; nada é gravado até clicar em **Salvar**.

- **Pastas:** **Abrir** a pasta dos **perfis** de todas as contas, o perfil de cada conta, a pasta de
  dados e a de logs (com o caminho e um botão para copiar). Nos perfis ficam os logins: não envie essas
  pastas para ninguém.
- **Geral, Intervalos e Farm:** as mesmas opções do `config.toml` (ver abaixo), com o limite de cada uma.
- **Contas:** nome, mascote (com prévia da sprite), hunt fixa e ativa/desativada.
- **Atalhos:** clique no campo e aperte a tecla nova; atalhos repetidos são recusados.
- **Desempenho:** liga e desliga o **Modo Leve** (ver *"Modo Leve"*).

Cada opção diz se **vale na hora** (nome, mascote, intervalos, farm, atalhos…) ou **só depois de
reiniciar o programa** (zoom inicial, Modo Leve…). Valores fora do limite são recusados, com a mensagem
no próprio campo. A roda do mouse rola a janela e **não** muda números nem listas: para mudar, clique no
campo e digite (ou use as setinhas). Ao salvar, o `config.toml` mantém os comentários e a ordem; a versão anterior fica em
`config.toml.bak`. **Restaurar padrão** volta uma seção (só grava ao salvar).

### Ou direto no config.toml

Em **Ajustes → Pastas**, abra a pasta de dados, abra o **`config.toml`** com o Bloco de Notas, salve e reabra o programa. Para cada
conta você pode mudar:

| Campo    | O que é |
|----------|---------|
| `nome`   | Nome que aparece no programa (ex.: `"Principal"`) |
| `pasta`  | Pasta do perfil em `profiles\` (não precisa mexer) |
| `sprite` | Número da Pokédex do mascote (1 a 386; ex.: 25 = Pikachu) |
| `hunt`   | Opcional. Deixe `""` para o programa usar o último mapa que a conta caçou |
| `ativa`  | `true` = pode ser iniciada; `false` = desativada |

Em instalações novas, `iniciar_contas_ao_abrir = true`: as contas ativas iniciam ao abrir,
com três segundos entre partidas (`intervalo_inicio_segundos`). Configurações antigas são preservadas;
ative em **Ajustes → Geral → Iniciar as contas ativas ao abrir o programa**.
**Nunca** coloque e-mail, senha, token ou cookie no `config.toml`.

### Início automático e bandeja (28/10/2026)

- Faça login uma vez em cada perfil e escolha uma hunt. Depois disso, a sessão salva e a última hunt
  permitem retomar o farm ao abrir. Uma hunt fixa em Ajustes tem prioridade. Sessão expirada,
  CAPTCHA, termos novos e criação de personagem ainda precisam da sua ação.
- Fechar no **X** ou minimizar envia para a bandeja e mantém as contas rodando. No menu do ícone:
  **Abrir PokeNexus** restaura; **Sair e parar as contas** encerra o programa e as sessões.
  Sem bandeja disponível, o X encerra normalmente. As opções ficam em Ajustes → Geral.
- **Abrir o programa na bandeja** é opcional. Não configura a inicialização junto com o Windows.
- Em segundo plano, a interface atualiza a cada cinco segundos e pausa as animações. Com
  **Ajustes → Desempenho → Usar a economia do jogo enquanto estiver em segundo plano**, o programa
  clica no controle de economia nativo. Ao restaurar, devolve a preferência anterior; quem já
  usava economia continua com ela ligada.
- Parar tudo também fecha o login reserva e cancela partidas que ainda estavam aguardando.
- Com **Avançar para a melhor hunt segura**, cada conta sem hunt fixa reaproveita o ranking do
  Hunt Analyzer. O objetivo pode ser XP do Pokémon, XP do treinador ou Ouro. A reavaliação padrão
  é a cada 15 minutos; áreas bloqueadas, inviáveis ou acima do risco escolhido são ignoradas e a
  troca exige pelo menos 5% de ganho. Medições de 10+ minutos corrigem o modelo de cada hunt para
  este PC e este Pokémon. Uma hunt fixa nunca é substituída por essa automação.
- O computador precisa continuar ligado, acordado e com internet. Login válido e uma área liberada
  continuam necessários. Não foi medida uma porcentagem de economia de CPU/RAM em contas reais.
- O limite simultâneo de quatro contas foi mantido. VM, proxy e troca de identificador não são
  usados para contornar as regras do servidor.

Validação e detalhes: [relatório](docs/automacao/RELATORIO.md).

## 3. Como o jogo aparece

O PokeIdle de cada conta roda **dentro da janela do PokeNexus**. Nenhuma janela de navegador é aberta.

- **Uma conta por vez:** clique na conta no topo (ou **Ctrl+1** … **Ctrl+4**). A troca é imediata e
  nada recarrega.
- **Todas ao mesmo tempo:** clique em **Todas as contas** (ou **Ctrl+0**). Cada conta aparece no seu
  quadro, com nome, nível, XP/h e status em cima. São as páginas **reais**: dá para clicar, rolar e
  digitar em qualquer quadro. Clicar num quadro seleciona aquela conta (o painel ao lado passa a
  controlá-la); **duplo clique no nome** do quadro abre só aquela conta.
- A grade se ajusta ao tamanho da janela, e o zoom de cada quadro é automático para o jogo caber.
- **📱 Celulares** (na barra de cima, só no Todas as contas): as contas ficam **em pé, lado a lado, como
  quatro celulares**, cada uma no **layout de celular do próprio jogo**. **▦ Grade** volta ao normal.
  Nada recarrega ao trocar (o jogo troca de layout sozinho pela largura da página), e a escolha fica
  salva (`layout_ver_todas` no `config.toml`, ou em Ajustes → Geral). Ao sair do Todas as contas,
  a conta volta ao layout de computador.

Na barra em cima do jogo: **−** / **+** (zoom, na visão individual) e **⟳** (recarregar a página da
conta selecionada). O botão **Registro** mostra/esconde a tabela e o log embaixo.

> Desempenho: na visão individual só a conta da tela é desenhada; no Todas as contas todas são desenhadas.
> Em computadores mais fracos, o **Modo Economia** do próprio PokeIdle (nas configurações do jogo)
> deixa tudo mais leve. O farm continua em todas as contas em qualquer modo.

## 4. Primeiro login (uma vez por conta)

1. Clique na conta (ex.: **Conta 1**).
2. Clique em **🔑 Login → Entrar aqui, na tela do jogo**. A conta inicia e mostra a tela de login.
3. Digite usuário e senha, marque *"Confirme que é humano"* e clique em **LOGAR**.
4. Pronto: o farm começa sozinho.
5. Repita para as outras contas, **cada uma com a sua conta do PokeIdle**.

Se a verificação *"Confirme que é humano"* não passar, use **🔑 Login → Entrar sem automação**: o
jogo abre sem nenhum monitoramento; entre na conta e clique em **▶ Já entrei — iniciar**.

O login dura cerca de 30 dias (o jogo renova sozinho enquanto você joga). As contas nunca
compartilham cookies, LocalStorage nem sessão.

### Primeira vez de cada conta: escolha o mapa

O farm acontece numa **área do Mapa (hunt)**. Na primeira vez o programa ainda não sabe onde cada
conta deve farmar: clique em **✋ Jogar eu mesmo**, abra o **Mapa** no jogo, escolha a área e
clique em **⟳ Retomar automação**. Daí em diante ele lembra sozinho.

## 5. Farm

- **▶ Iniciar** (painel da conta) inicia só aquela conta; **▶ Começar tudo** inicia as ativas (até 4).
- **■ Parar tudo** pergunta antes (*"Parar tudo as N contas conectadas?"*): só para com **Sim**.
- Todas as contas iniciadas farmam ao mesmo tempo, estejam na tela ou não.

O que o programa faz sozinho:

- entra na área de farm (pelo Mapa do jogo);
- acompanha as batalhas (que o próprio servidor do jogo executa) e conta o XP;
- se o time for nocauteado, cura no Centro Pokémon e volta para a área (se a opção **"Voltar à hunt
  ao morrer"** do próprio jogo estiver ligada, ele espera o jogo fazer isso primeiro);
- se o time cair **3 vezes em 15 minutos**, **pausa** a conta para você não perder XP em sequência;
- se a internet cair ou o jogo parar de responder, recarrega a página e tenta de novo;
- se a página de uma conta travar, reabre só aquela conta;
- se a página de uma conta passar de **2.000 MB** de memória por alguns minutos (o jogo vai
  acumulando memória ao longo de muitas horas), reabre só aquela conta, entre uma batalha e outra e
  só no farm automático (nunca em modo manual ou pausado). O limite é `limite_memoria_pagina_mb` no
  `config.toml` (`0` desliga).

O que o programa **nunca** faz (são coisas para você fazer): login, aceitar termos novos, criar
personagem, escolher o pokémon inicial, comprar itens, ou "tomar" a conta de volta quando ela foi
aberta em outro lugar.

## 6. Controle manual

1. Selecione a conta (no topo, **Ctrl+1** … **Ctrl+4**, ou clicando no quadro dela no Todas as contas).
2. Clique em **✋ Jogar eu mesmo**.

Só aquela conta para de ser automatizada (status **MANUAL**); as outras continuam farmando. Jogue
direto na tela: clicar, rolar, abrir menus, digitar — tudo funciona como num navegador.

- **❚❚ Pausar** (ou **F8**) também para a automação da conta.
- Para voltar: **⟳ Retomar automação** (ou **F8**). Antes de agir, o programa **confere de novo o
  estado atual do jogo** — não assume que nada ficou igual.
- Num **Boss**, na **Arena Mística** ou dentro da **Casa**, o programa não mexe até você sair de lá.

## Modo Leve (para PCs mais fracos)

Liga e desliga em **Ajustes → Desempenho**. Depois de salvar, **reinicie o PokeNexus** (feche e
abra de novo): o modo só é aplicado quando o programa abre. Quando ligado, o rodapé mostra "Modo Leve".

**Tudo funciona igual** — farm, login, Todas as contas (clicar e jogar em qualquer quadro), controle manual,
Hunt Analyzer com "Caçar aqui", atalhos, Parar tudo. Só a aparência fica mais simples:

- sprites paradas (a imagem de sempre, sem animação) e selos de status sem piscar;
- fundo liso (sem o xadrez) e mascote sem o brilho em volta;
- números da tela atualizados a cada 1 s (os comandos continuam imediatos) e menos linhas de log na
  tela (o arquivo de log continua completo);
- páginas do jogo com **"reduzir movimento"**, que o próprio PokeIdle respeita desligando as animações
  de enfeite;
- **Leve 2.0:** com placa de vídeo, as páginas continuam desenhadas por ela (o Leve antigo desligava a
  placa e, num PC com placa, isso deixava o jogo mais travado: 38,8 × 60 quadros/s numa conta). Num PC
  **sem** placa, o Chromium e o Qt desenham por software, pelo caminho mais barato para a CPU
  (`QT_QUICK_BACKEND=software`). A escolha é automática a cada abertura. Medidas e ferramenta em
  `docs/desempenho/` e `ferramentas/desempenho/`.

Nada disso mexe no ritmo do jogo: as páginas escondidas continuam rodando normalmente. O PokeIdle
também tem o **Modo Economia** nas configurações do próprio jogo (desliga a cena do mapa); ele economiza
ainda mais e pode ser ativado pelo PokeNexus em segundo plano, conforme a opção em Ajustes.

## 7. Hunt Analyzer (Hunts)

Mostra **onde vale mais a pena caçar** com o pokémon que está em campo na conta selecionada. Abra
pelo botão **Hunts** em cima do jogo (ou **Ctrl+H**); **🎮 Jogo** volta para o jogo. As páginas
continuam rodando por trás: o farm não para.

- **Pokémon em campo:** sprite, nível, potência/qualidade, IVs, stats, TM e os bônus de XP ativos
  (VIP, XP Boost, guild, Boost da Guild, Twitch, Kick, evento, atrasados).
- **Melhor hunt agora:** XP/h do pokémon e do treinador, ouro/h, abates/h, tempo para derrotar, golpe
  recomendado, risco (Baixo / Médio / Alto, com o pior golpe recebido) e os selvagens da área.
  **Caçar aqui** leva a conta para lá pelo Mapa do jogo, do mesmo jeito que o farm faz (respeitando
  as travas do jogo: 3 s sem troca de golpes e a porta do mapa).
- **Ranking:** todas as hunts com XP/h, Ouro/h, Abates/h, tempo, risco e o medido de verdade; ordene
  por **XP/h, Ouro/h, Abates/h ou Risco**. Hunts que exigem nível de treinador maior aparecem com 🔒
  (com *"Mostrar apenas hunts disponíveis"* desmarcado). Cada linha tem o seu botão **Caçar**.
- A **hunt atual** fica destacada (◉), mas **não ganha vantagem** no cálculo: o ranking é sempre a
  estimativa de onda cheia, igual para todas.
- **Estimativa × real:** o desempenho medido na caçada atual e o histórico de abates/h deste pokémon
  em cada hunt aparecem à parte, só como referência.
- As opções (ordenação, *"Mostrar apenas hunts disponíveis"*, *"Considerar poção automática"*) são
  **salvas por conta**.

Os cálculos seguem as mesmas fórmulas da extensão **"/hunt for PokeIdle"** (v1.0.1), refeitas dentro
do PokeNexus — não precisa da extensão, do Chrome nem de nenhum serviço externo. A atualização 1.287
do jogo tirou uma função que a extensão usava (por isso ela parou de funcionar); o PokeNexus faz essa
conta sozinho — a amplificação da efetividade na hunt, como a Pokepédia do jogo descreve — e segue
dando os mesmos números. As partes que são do
jogo (catálogo de espécies, efetividade de tipos, XP e ouro por abate, recarga dos golpes, bônus) são
lidas dos **arquivos públicos do próprio jogo, da versão que está no ar**, numa página separada, sem
login. O cálculo só é refeito quando muda algo que entra nele (pokémon, nível, stats, bônus, versão do
jogo, opções ou a medição das hunts).

## 8. Mercado da Comunidade (Mercado)

> ⚠️ **Mexe com dinheiro de verdade.** A **Gema** é comprada com USDT e volta em USDT. Comece com um
> item barato e poucas unidades. O PokeNexus **nunca** deposita nem saca Gemas, nunca mexe em USDT,
> carteira, PIX ou cartão, e nunca compra diamantes nem itens da Loja — isso é sempre seu.

O botão **Mercado** em cima do jogo (ou **Ctrl+M**) abre a **lista de compras da conta selecionada**. O
PokeNexus compra com os mesmos pedidos que os botões do Mercado da Comunidade mandam, sem abrir a tela. Os Termos do
PokeIdle permitem automação no Mercado (seção 5).

- **Adicionar item:** escolha o **item** (da lista do próprio jogo), a moeda (**Ouro** ou **Gema**) e o
  **preço máximo por unidade** (obrigatório). Exemplo: Ultra Ball até 100 de ouro cada — ele nunca paga
  mais que 100 por unidade. Usa a "compra em quantidade" do jogo: o próprio servidor confere o preço
  máximo e o total antes de comprar. O item entra **Desligado**.
- **Ligado / Desligado:** cada item tem o seu botão. Ligar pede confirmação com o resumo (conta, item,
  moeda, preço máximo, limites). Ligado, ele compra sempre que achar até o seu preço e **continua ligado
  depois de fechar e abrir o PokeNexus**. Clicar em **Ligado** desliga na hora.
- **Limites (opcionais, todos desligados no começo):** parar depois de X unidades, parar depois de
  gastar X, gastar no máximo X por dia. **Sem nenhum limite ele compra sem parar até você desligar** —
  a confirmação diz isso com essas palavras. Na **Gema**, a confirmação avisa em destaque que é dinheiro
  de verdade e só libera depois de marcar "Entendi que a Gema vale dinheiro de verdade". Os limites
  mudam em **Editar**, com o item desligado.
- **Status ao vivo:** cada item mostra o que está fazendo: *Procurando* (com o menor preço do momento),
  *Comprou N por P*, *Esperando dinheiro*, *Limite do dia*, *Parado: motivo* ou *Desligado: motivo*.
  Embaixo ficam os contadores de hoje e do total (unidades e gasto) e a última compra; só contam
  compras de verdade.
- **Compra na liberação (sem abrir nada na tela):** no jogo, todo anúncio novo fica **retido 2 min**
  antes de poder ser comprado. O PokeNexus olha a vitrine de cada item ligado pela própria conexão do
  jogo, de quanto em quanto você escolher (**Olhar a vitrine a cada**, padrão 60 s), sem abrir a janela
  do mercado: a tela do jogo não pisca e o farm continua. Achou anúncio até o seu preço ainda retido? A
  compra fica **marcada para o segundo em que ele libera** (o status mostra a hora) e sai **um pedido**
  nessa hora. Quem pede nos primeiros 3 s entra no sorteio do jogo; perder não custa nada. Anúncio já
  liberado é comprado na hora. Sem dinheiro, ele espera e volta sozinho quando entrar dinheiro.
- **Segurança (vale também sem limite):** nunca compra anúncio das suas outras contas do PokeNexus
  ("Nunca comprar anúncio das minhas outras contas", ligado por padrão), duas contas suas nunca pedem o
  mesmo anúncio, cada anúncio é pedido uma vez só, e **3 recusas seguidas do jogo desligam o item**.
  Com a conta sem conexão, no login ou com a automação pausada ele **só espera** (Parado). Batalha e
  controle manual não atrapalham, porque nada é clicado.
- **Parar todas as compras** desliga na hora todos os itens, em todas as contas.
- **Venda:** a venda automática saiu desta versão. As regras de venda antigas ficam guardadas
  (desligadas) no arquivo novo.
- **Arquivos:** a lista fica em `profiles\conta_XX\rmt_compras.json`; o extrato das compras em
  `profiles\conta_XX\rmt_extrato.jsonl`. Na primeira abertura, as regras de compra antigas
  (`rmt_regras.json`) viram itens **desligados**, com os mesmos limites; o arquivo antigo não é apagado.

**Calculadora de Gemas:** o botão **Calculadora**, no cartão do Saldo, abre uma conta de Gemas para
dólares e de dólares para Gemas, com o Meowth dando palpite. A taxa é de **referência** (1.000 Gemas =
US$ 9,00), não é cotação nem saque. Digitar num campo atualiza o outro; as fichas **100**, **1.000**,
**10.000**, **Meu saldo** (as Gemas da conta, com ela conectada) e **Saldo de todas as contas** (a soma das
Gemas das contas conectadas; a dica diz quantas) preenchem as Gemas. Ela **só calcula**:
não compra, não liga item, não grava nada e não acessa a internet. Aberta ou fechada vale até você fechar o
programa. A taxa fica em `app/conversor_gemas.py` (`GEMAS_REF`, `CENTAVOS_REF`) e as falas do Meowth em
`app/textos_guia.py` (`FRASES_MEOWTH`).

**Guia:** o botão **Guia** (no alto do Mercado) mostra, passo a passo, para que serve cada parte: ele
destaca a parte, explica e segue com **Próximo** (ou Enter / seta para a direita), **Voltar** (seta para
a esquerda) e **Pular guia** (ou Esc). O guia só explica: não clica em nada, não liga item e não muda
nenhum limite. Na primeira vez que você abre o Mercado aparece o convite "Primeira vez aqui?"; depois de
abrir o guia ou fechar o convite, ele não volta (fica salvo em `[janela] guia_mercado_visto`). Os textos
do guia estão em `app/textos_guia.py`.

## 9. Pokédex

O botão **Pokédex** no alto da janela (ou **Ctrl+D**) abre a Pokédex da conta selecionada na área do jogo. As
contas continuam caçando por trás; **Jogo** (ou Ctrl+D de novo) volta. Ela **só mostra**: não captura, não clica
no jogo e não manda nada ao servidor.

- **Quem entra:** os pokémon que o PokeNexus tem desenho **e** que existem no jogo no ar: hoje 385 (Kanto 151,
  Johto 99, Hoenn 135; o Unown fica de fora por falta de desenho). A lista se monta sozinha: espécie nova do
  jogo que tenha desenho aparece.
- **Pego ou não:** quem a conta ainda não tem aparece como **silhueta preta**, sem nome. Quem ela já tem aparece
  colorido, com o nome e uma Pokébola no canto. Conta o que a **Pokédex do próprio jogo** registra como capturado
  e o que está no **inventário** da conta (inclusive o Depot e os que vieram de evolução ou troca), então o
  número pode passar o da aba do jogo. Mega e Forma seguem o jogo (entrada própria, não marcam a espécie base).
- **Em cima:** a barra "123 de 385", a porcentagem e Kanto/Johto/Hoenn. **Esta conta** ou **Todas as contas**
  (vale se qualquer conta tiver; a dica diz qual). Filtros por região, busca por número (qualquer um) ou por nome
  (só dos que você já tem, para não estragar a surpresa) e "Mostrar só os que faltam".
- **Dica no mouse:** nome, número, tipos, a primeira captura e "No inventário". O selo **Novo** marca o que
  chegou nas últimas 24 h. A telinha da esquerda mostra o pokémon em que o mouse está.
- **Arquivos:** `profiles\conta_XX\pokedex.json` (só números e datas; abre com a conta parada) e
  `pokedex_especies.json` na pasta de dados (nomes e tipos, para abrir sem internet).

## Aparência

O PokeNexus tem visual próprio, o tema **"Base do Treinador"**: molduras de madeira escura em pixel art,
como as do próprio PokeIdle, para o programa e o jogo parecerem uma coisa só. Os ícones, as molduras, o
logo e o ícone do programa são **arte própria**, desenhada por código em `ferramentas/arte/` (rode
`gerar_ui.py` e `gerar_marca.py` de novo depois de mudar uma cor em `app/tema.py`). As fontes são a
**Jersey 10** e a **Nunito**, as duas com licença SIL OFL (`assets/fonts`). **F1** mostra os atalhos.

## Atalhos

| Tecla | Ação |
|-------|------|
| Ctrl+1 … Ctrl+4 | Mostra a conta 1 … 4 |
| Ctrl+0 | Todas as contas |
| Ctrl+H | Alterna entre o jogo e o Hunt Analyzer (Hunts) |
| Ctrl+M | Alterna entre o jogo e o RMT (Mercado) |
| Ctrl+D | Alterna entre o jogo e a Pokédex |
| F8 | Pausa / retoma a automação da conta selecionada |
| Ctrl+, | Abre os Ajustes |
| Ctrl+B | Esconde / mostra a ficha do treinador |
| F1 | Atalhos e ajuda |

Funcionam com a janela do PokeNexus em foco (inclusive com o cursor dentro do jogo) e podem ser
trocados em **Ajustes → Atalhos** (valem na hora) ou no `config.toml`.

## Painel e status

- **Abas no topo:** status, nível e XP/h de cada conta. Se o pokémon em campo (o que está sendo
  upado) for **Bulbasaur, Charmander ou Squirtle**, a aba mostra ele; com qualquer outro, fica o
  mascote da conta.
- **Painel da conta:** mascote, status, nível do treinador, XP ganho, XP/h, tempo ativo, batalhas
  (uma batalha = uma onda de selvagens), área, última batalha e última ação. O botão de setas no canto
  da ficha esconde ela e o jogo fica mais largo (vale também no Todas as contas); **Ficha**, em cima do
  jogo, ou **Ctrl+B** mostra de novo. Nada recarrega, e o programa lembra da escolha.
- **Registro** (botão no topo): todas as contas numa tabela e tudo o que aconteceu (também salvo
  em `logs\AAAA-MM-DD.log` na pasta de dados).

Os números vêm das mensagens do próprio jogo. Quando algo ainda não pode ser medido aparece **—**
(nada é inventado). O XP/h só aparece depois de 1 minuto e da primeira batalha.

| Status | Significado |
|--------|-------------|
| 🟢 FARMING | Na área de farm, tudo certo |
| 🟠 BATALHA | Batalha acontecendo agora |
| 🔵 AGUARDANDO / INICIANDO | Conectando, entrando na área, no Centro ou esperando algo |
| 🟣 PAUSADO | Automação pausada |
| 🩵 MANUAL | Você está no controle |
| 🔴 ERRO | Algo deu errado (veja o texto embaixo do status e o log) |
| 🩷 SESSÃO EXPIRADA (LOGIN) | Precisa fazer login |
| ⚫ OFFLINE | Conta parada |

## Problemas comuns

**A conta fica em SESSÃO EXPIRADA** — o login dela não existe ou venceu. Use **🔑 Login**.

**"Já há 4 contas conectadas"** — é o limite dos Termos do PokeIdle. Pare uma conta antes. O topo mostra
só as contas **jogando** de verdade (ex.: "0/4 jogando"); conta iniciada com erro não aparece ali, mas
continua contando no limite (passe o mouse no contador para ver iniciadas e com erro).

**"Não consegui achar o endereço do PokeIdle" (ERR_NAME_NOT_RESOLVED)** — o DNS do Windows não achou o
site. O programa já tenta um DNS seguro (Cloudflare e Google) e repete sozinho em alguns segundos. Se o
site abre no navegador mas não no PokeNexus, troque o DNS do Windows: **Win+R** → `ncpa.cpl` → botão
direito no adaptador da internet → **Propriedades** → **Protocolo IP Versão 4 (TCP/IPv4)** →
**Propriedades** → em cima *"Obter um endereço IP automaticamente"*, embaixo *"Usar os seguintes
endereços de servidor DNS"*: `1.1.1.1` e `8.8.8.8` → OK. Depois, no Prompt de Comando:
`ipconfig /flushdns`. Para testar, desative também adaptadores de VPN (ex.: Radmin). Os outros erros de
rede também aparecem em português; o código original fica na dica do mouse e no log.

**ERRO "conta aberta em outro lugar"** — a mesma conta foi aberta em outro navegador/celular. Só uma
sessão joga por vez. Para jogar pelo PokeNexus: **Jogar eu mesmo** → *"Jogar aqui"* no jogo →
**Retomar automação**.

**ERRO "limite de contas conectadas nesta rede"** — o servidor recusou porque já há contas demais
conectadas na sua internet (inclusive em outros aparelhos da casa).

**AGUARDANDO "escolha uma área no Mapa"** — veja *"Primeira vez de cada conta: escolha o mapa"*.

**A conta foi PAUSADA sozinha ("muitas derrotas seguidas")** — o time está caindo demais nessa área.
Troque de área ou fortaleça o time e clique em **Retomar automação** (limite: `max_derrotas`).

**O "Confirme que é humano" não passa** — use **🔑 Login → Entrar sem automação**.

**O jogo ficou pequeno/grande demais** — use **−** / **+**, esconda o **Registro** ou arraste
as divisórias. O zoom inicial fica em `zoom` no `config.toml`.

**O programa não abre** — veja `logs\crash.log` na pasta de dados (`%LOCALAPPDATA%\PokeNexus`).

**Quero começar do zero uma conta** — feche o programa e apague `profiles\conta_XX` na pasta de dados.

---

## Para o desenvolvedor

### Rodar a partir do código

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### Como publicar uma versão

**Todo commit na `main` publica uma versão** pelo GitHub Actions (`.github/workflows/release.yml`):
1. **Trava 1:** falha se algum arquivo rastreado for login, log ou dado de conta (`profiles/`, `logs/`,
   `*.log`, `Local Storage`, `Cookies`, `leveldb`, `manager_state.json`, `rmt_*.json`).
2. Build com o PyInstaller nas versões exatas de `instalador/requirements-build.txt`.
3. **Trava 2:** abre o `PokeNexus.exe` gerado por 25 s (`instalador/fumaca.ps1`), confere que não
   fechou nem gravou `crash.log`, fecha e confere que não sobrou processo.
4. Gera o ZIP, o instalador (Inno Setup, `instalador/PokeNexus.iss`) e o `SHA256SUMS.txt`, e cria a
   Release `v<versão>` (a mais nova fica "Latest") com as mensagens dos commits como notas.

A versão é `APP_VERSION_BASE` (`app/config.py`, hoje `1.1`) + o número da execução do Actions: `1.1.57`.
Para uma versão nova "grande", troque a base (`1.2`). Rodando do código a versão aparece como `1.1-dev`
e o aviso de atualização fica desligado.

**Não publica:** commit com **`[sem atualização]`** na mensagem, ou que só mexe em `docs/`, `*.md` ou
`ferramentas/`. Também dá para publicar à mão em Actions → "Publicar versão" → Run workflow.

Nunca coloque token ou senha no programa: o repositório é público e o aviso consulta as Releases sem
login. Releases só saem pelo Actions, com as travas.

### Gerar o programa na sua máquina

1. Dê dois cliques em **`build.bat`** (precisa de Python só na máquina de quem gera).
2. Saída:
   - `dist\PokeNexus\PokeNexus.exe` (pasta pronta para rodar);
   - `dist\PokeNexus-<versão>.zip`;
   - `dist\PokeNexus-Setup-<versão>.exe`, se o **Inno Setup 6** estiver instalado (sem ele, só o ZIP).

Sem nada, o build local sai como `1.1-dev` (sem aviso de atualização). Para testar o aviso, defina antes
`set VERSAO_BUILD=1.1.5`. Os testes do aviso (servidor falso de Releases, builds de teste) estão em
`ferramentas/atualizacao/` e `docs/atualizacao/RELATORIO.md`.

O build usa o **PyInstaller** (`PokeNexus.spec`) em modo pasta: o executável leva junto o Python, o
PySide6 e o **Qt WebEngine** (o motor Chromium que exibe o jogo), além das pixel arts e do
`config.toml` padrão. O modo de arquivo único foi evitado de propósito: com o Qt WebEngine ele
extrairia ~300 MB para uma pasta temporária a cada abertura. O `PokeNexus.spec` leva só os módulos
do Qt que o programa e o `QtWebEngineProcess.exe` carregam de verdade (sem QML, sem recursos de
depuração, sem o painel visual do DevTools, com os idiomas do navegador em inglês, português e
espanhol).

**Para mandar a amigos testarem:** depois do build, rode
`powershell -ExecutionPolicy Bypass -File ferramentas\pacote_amigos\montar.ps1` (ou com
`-Origem dist_novo\PokeNexus`). Sai `dist\PokeNexus-<versão>-para-amigos.zip` com a pasta do programa, um
`LEIA-ME.txt` (instalar, aviso do Windows, login, regras, Modo Leve, atualizar) e o
`Juntar relatorio para enviar.bat`, que junta os logs e o `config.toml` num ZIP na Área de Trabalho
(nunca a pasta `profiles`, com os logins). O `config.toml` da pasta de dados de quem já usou uma versão
antiga não é trocado; as mudanças de padrão que precisam chegar nele ficam em `app/config.py`
(`_migrar_config`, uma vez só, marcadas em `migracoes.txt`).

`POKENEXUS_DATA=<pasta>` troca a pasta de dados (útil para testes; nada é migrado para ela).

### Estrutura

```
main.py                     ponto de entrada
config.toml                 configuração padrão (copiada para a pasta de dados)
PokeNexus.spec, build.bat   build do executável
instalador/                 instalador (Inno Setup), teste de fumaça e versões exatas do build
.github/workflows/release.yml  publica a versão (Release) a cada commit na main
app/atualizacao.py          aviso de atualização (procura, faixa, download, SHA-256, instala)
app/config.py               caminhos (programa x dados do usuário) e leitura da configuração
app/manager.py              loop asyncio com um worker por conta, watchdog, logs
app/gui.py, app/widgets.py  interface PySide6 (visão individual e Todas as contas)
app/hunt_ui.py              painel Hunts (só desenha)
app/settings_ui.py          janela Ajustes
app/rmt_ui.py               painel Mercado (lista de compras, ligar/desligar, limites, status, calculadora)
app/conversor_gemas.py      a conta da calculadora de Gemas (taxa de referência, Decimal, sem Qt)
app/pokedex_ui.py           a Pokédex na tela (grade com delegate, silhuetas, Todas as contas)
game/pokedex.py             a Pokédex sem tela: quem entra, quem foi pego, o arquivo de cada conta
app/guia.py, app/textos_guia.py  guia passo a passo do Mercado e os textos dele
rmt/compras.py              a lista de compras de UMA conta (no perfil dela) e a migração das regras antigas
rmt/regras.py               formato antigo (regras v1), usado só para migrar
rmt/taxas.py                comissão do Mercado (a mesma conta do shared/taxa-mercado.mjs do jogo)
rmt/decisao.py              o que um item compraria agora (sem rede: testável)
rmt/mercado.py              as ações pelos botões do Mercado do jogo (clique protegido) + respostas
rmt/rotina.py               a rotina do Mercado por conta: olha a vitrine e compra na liberação
rmt/canal.py                manda os pedidos do Mercado pela conexão do jogo (sem abrir tela)
app/config_edit.py          validação e gravação do config.toml mantendo comentários
workers/account_worker.py   sessão de UMA conta + recuperação de erros + estatísticas
workers/farm_worker.py      a rotina de farm (decide o que fazer a cada verificação)
hunts/bridge.js             ponte com os módulos do jogo (catálogo e fórmulas da versão no ar)
hunts/game_data.py          página de dados anônima do Hunt Analyzer (sem login, sem janela)
hunts/calculator.py         motor do Hunt Analyzer (port do engine.js do /hunt)
hunts/measure.py            medição real das hunts (geometria das ondas e abates/h) por conta
hunts/analyzer.py           analisador de UMA conta: assinatura, cache, opções, ranking
browser/web_host.py         páginas Qt WebEngine embutidas (uma por conta, perfil próprio)
browser/cdp.py              cliente DevTools ligado a cada página (WebSocket, DOM, navegação)
browser/browser_manager.py  abre/fecha as sessões
browser/proc_mem.py         memória dos processos de página (vigia de memória)
game/pokeidle.py            leitura das mensagens do jogo (WebSocket) e ações no DOM
game/selectors.py           IDs do DOM do PokeIdle
assets/                     pixel arts e ícone
```

Como o jogo funciona (lido do `app.js` do PokeIdle): o login fica no LocalStorage (`sessao`), a
página conversa com o servidor por WebSocket, o servidor manda o estado do jogador (`welcome` /
`estado`, com `ondaSeq` numerando as ondas de selvagens) e os eventos de luta (`batalha`: `spawn`,
`ataque`, `morte`, `fugiu`, `centro`...). O programa só **escuta** essas mensagens (pelos eventos
`Network.*` do DevTools, sem injetar nada na página) e usa o DOM (botões do jogo) para agir. O
DevTools escuta só em `127.0.0.1`, numa porta sorteada a cada execução.

Por que não Playwright: o Qt WebEngine não aceita a conexão "de navegador inteiro" que o Playwright
exige (`Browser context management is not supported`); por isso cada conta conversa com a própria
página por um cliente DevTools simples (`browser/cdp.py`). Isso também dispensa distribuir um
Chromium separado: o motor já vem dentro do PySide6.
