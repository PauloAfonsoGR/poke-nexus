# Segundo plano: o X manda o PokeNexus para a bandeja

13/11/2026. Pedido: `PROMPT` "Modo em segundo plano" (o X esconde na bandeja com as contas farmando; Sair de
verdade só pelo ícone; uma cópia só).

## O que já existia (PR #1, 29/10/2026) e o que mudou agora

O PR #1 já tinha `app/bandeja.py`, o X e o minimizar escondendo na bandeja, a interface a cada 5 s escondida,
as sprites pausadas e as opções em Ajustes → Geral (`fechar_para_bandeja`, `minimizar_para_bandeja`,
`iniciar_na_bandeja`). O prompt pedia "nenhuma opção nova no Ajustes": **nenhuma foi criada**; as três que já
existiam ficaram como estavam (mesmos padrões, `app/config.py` e `config.toml` sem mudança).

Faltava, e foi feito:

| Item | Onde |
|---|---|
| Aviso do Windows (balão) na 1ª ida para a bandeja de cada sessão, nada gravado em disco | `app/bandeja.py` `avisar_primeira_vez` |
| Menu do botão direito: status só leitura ("4 contas jogando", "…, 1 com erro"), **Abrir PokeNexus**, **Sair**; no tema | `app/bandeja.py` |
| Dica do ícone: "PokeNexus" + o mesmo resumo, pela mesma contagem do contador do topo (`_contagem`) | `app/gui.py` |
| Voltar **como estava**: antes `restaurar()` usava `showNormal()` e a janela maximizada voltava *não* maximizada (medido) | `app/gui.py` `restaurar` |
| **Um método só para fechar de verdade:** `MainWindow.sair()` (bandeja → Sair, fim de sessão, atualizador). O X com a bandeja desligada em Ajustes usa o mesmo `_parar_tudo` | `app/gui.py` |
| Fim de sessão do Windows e Restart Manager do instalador: `commitDataRequest` → `sair()`; `aboutToQuit` como rede de segurança. **Antes nada parava as contas nesses casos** | `app/gui.py` |
| `setQuitOnLastWindowClosed(False)`: fechar um aviso com a janela escondida não encerra o programa sem parar as contas | `main.py` |
| Atualizador chama `sair()` | `app/atualizacao.py` |
| **Uma cópia só** por pasta de dados | `app/instancia.py` (novo), `main.py` |
| Teste de fumaça do build (trava do Actions) fechava "no X" e exigia que o processo saísse: com a bandeja isso falharia. Agora: X → confere que escondeu → fecha pelo fim de sessão (o caminho do Sair) | `instalador/fumaca.ps1`, `ferramentas/atualizacao/teste_app.ps1` |
| Textos: F1, `README.md`, `AGENTS.md` | |

### Uma cópia só (`app/instancia.py`)

Mutex do Windows `Local\PokeNexus-<hash(usuário + pasta de dados)>` + `QLocalServer` com o mesmo nome (só o
mesmo usuário conecta). Ao abrir, antes de ler a configuração ou criar página/perfil:

- mutex livre → esta é a cópia; grava o PID em `<dados>\instancia.pid` e escuta;
- mutex ocupado → pede "mostrar" à outra; resposta "ok" → sai com código 0; "saindo" → espera até 90 s ela
  terminar e abre;
- sem resposta em 15 s (viva e travada) → pergunta "Fechar o que está travado e abrir de novo?" (padrão:
  Cancelar). Só fecha se o PID do arquivo for o mesmo programa (`PokeNexus.exe`/`python.exe`);
- cópia que morreu (travamento, "Finalizar tarefa") → o Windows solta o mutex sozinho: abre na hora.
- A cópia nova chama `AllowSetForegroundWindow` para a janela da outra poder vir para a frente.

`POKENEXUS_DATA` diferente = nome diferente = cópias independentes.

## Os 7 riscos

Medido com `ferramentas/bandeja/medir_segundo_plano.py`: o PokeNexus de verdade (mesma janela, mesmas
páginas, mesmo Manager) com 4 contas num **jogo simulado** em 127.0.0.1 (WebSocket com `estado` e `batalha` a
cada 0,2 s). Contadores dentro da página, CPU/memória da árvore de processos, EcoQoS e prioridade de cada
processo. **Sem contas reais** (ver "Falta").

### Tabela visível × minimizada × bandeja (5 min por fase, 4 contas)

| | Visível | Minimizada | Bandeja |
|---|---|---|---|
| Batalhas por minuto (por conta) | 315,5 a 315,7 | 317,4 | 317,0 a 317,2 |
| Mensagens do WebSocket recebidas pela página /s | 10,56 | 10,62 | 10,61 |
| `setInterval` de 100 ms, disparos /s (o freio do Chromium baixaria para 1/s) | 10,01 | 10,01 | 10,01 |
| Clique `element.click()` até a resposta do servidor chegar na página (mediana / máx.) | 0,7 / 10,7 ms | 0,7 / 1,2 ms | 0,7 / 1,3 ms |
| CPU da árvore (% da máquina) | 1,34% | 0,41% | 0,40% |
| Memória privada da árvore (média) | 340 MB | 346 MB | 362 MB |
| Processos em modo de eficiência / com EcoQoS | 0 / 0 | 0 / 0 | 0 / 0 |
| Prioridade dos 5 processos | normal | normal | normal |
| `document.visibilityState` | visible (conta à vista) | hidden | hidden |
| `requestAnimationFrame` /s | 60 (conta à vista) | 0 | 0 |

As fases rodaram uma depois da outra; a memória sobe com o tempo em todas (as páginas acumulam), não por
causa do esconder (outra rodada de 2 min: 314 / 312 / 328 MB). Variação das batalhas entre fases: < 1%.

1. **Páginas escondidas continuam rodando:** sim. Timers sem freio (10/s), WebSocket com a mesma taxa,
   batalhas iguais. Só o desenho (`requestAnimationFrame`) para, igual à janela minimizada e às contas fora da
   tela que já existiam; as `CHROMIUM_FLAGS` não precisaram mudar (`browser/web_host.py` intacto).
2. **Cliques do farm escondido:** o farm clica por `Runtime.evaluate` + `element.click()` (`browser/cdp.py`,
   `game/selectors.py`), não por eventos de mouse/teclado, então não depende de a página estar desenhada.
   Provado: clique → resposta 0,7 ms nas três fases; página **recarregada com a janela escondida** voltou a
   caçar sozinha em 1,6 a 3,6 s (o farm clicou em "Caçar" escondido).
3. **Modo de eficiência do Windows 11:** nenhum processo (`python.exe`/`PokeNexus.exe` e os 4
   `QtWebEngineProcess.exe`) com EcoQoS nem prioridade ociosa em nenhuma fase (lido a cada 5 s por
   `GetProcessInformation(ProcessPowerThrottling)` e `GetPriorityClass`).
4. **Vigias:** rodam na thread do Manager, sem depender da janela. Com a janela escondida e os tempos
   encurtados só na memória do teste: renderer de uma conta travado → "worker travado" em 22 a 29 s (vigia em
   20 s) → só aquela conta reiniciou e voltou a caçar em 24 a 31 s; vigia de memória com limite baixo →
   "reabrindo só esta conta" em 13,5 a 17,5 s e as 4 contas caçando depois.
5. **Mercado, compra na liberação:** a hora da compra é marcada por `asyncio.sleep` na thread do Manager
   (`rmt/rotina.py`), e o pedido sai pela página. Medido o mesmo caminho (dormir até a hora marcada e mandar um
   pedido pela página): atraso mediano **31,5 / 32,0 / 32,0 ms** (visível / minimizada / bandeja), máximo 63 ms
   nas três. Não piora escondido. (Sem compra real: o prompt manda desligar os itens no teste com conta real.)
6. **Voltar:** a página aparece desenhada já 300 ms depois de mostrar (cor da página lida dos pixels da TELA,
   não da memória), `visibilityState` volta a `visible` e o desenho a 61 a 64 quadros/s; mesma conta (Conta 2),
   mesma tela, maximizada, mesmo tamanho da página (1531×771), mesmo zoom (100%) e layout do Todas. Janela
   não maximizada volta no mesmo lugar e tamanho (`120,90,1420,910` → igual). `voltou_da_bandeja.png`.
7. **Sair:** sem sobra de processo em 20 de 20 fechamentos medidos com espera de 60 s (Sair, fim de sessão escondida e visível, Restart Manager; 5 rodadas). Numa rodada anterior do
   teste (que esperava só 15 s e não guardava os nomes) 4 processos ainda estavam vivos 15 s depois do Sair;
   não repetiu em 5 rodadas seguidas (4 do código + 1 do `.exe`), em todas sumiram na hora. Fica anotado.

## Fluxos (`ferramentas/bandeja/teste_fluxos.py`)

O PokeNexus em outro processo, como o usuário abre, com pasta de dados temporária (contas na tela de login).
O teste manda as mensagens que o Windows manda: `WM_CLOSE` (X), `WM_SYSCOMMAND/SC_CLOSE` (Alt+F4), a mensagem
do ícone da bandeja (clique, duplo clique, botão direito), teclas no menu e no aviso, `WM_QUERYENDSESSION` +
`WM_ENDSESSION` e o **Restart Manager** do Windows (`RmShutdown`, o que o Inno Setup usa no `CloseApplications`).
Não move o mouse.

| Fluxo | Código (5 rodadas) | `.exe` do ZIP, sem Python no PATH |
|---|---|---|
| Abre maximizada | ok | ok |
| X esconde, processo continua | ok | ok |
| Clique no ícone mostra, maximizada | ok | ok |
| Alt+F4 esconde | ok | ok |
| Duplo clique mostra | ok | ok |
| Minimizar vai para a bandeja e volta maximizada | ok | ok |
| Janela normal volta no mesmo lugar e tamanho | ok | ok |
| Abrir de novo com o programa escondido: mostra a primeira e sai | ok (0,5 s, código 0) | ok (0,4 s) |
| Menu → Abrir PokeNexus | ok | ok |
| Menu → Sair, sem sobrar processo | ok (4 de 5, ver risco 7) | ok |
| Pastas de dados diferentes abrem juntas | ok | ok |
| Fim de sessão do Windows com a janela escondida: sai pelo Sair (linha no log) | ok (0,4 a 1,4 s) | ok (0,2 s) |
| Restart Manager com a janela escondida | ok (python: tipo console) | ok (tipo janela, 0,2 s) |
| Cópia anterior morta não impede abrir | ok (0,8 s) | ok (0,7 s) |
| Cópia travada: aviso, "Fechar e abrir", abre, não sobra processo | ok (aviso em ~16,5 s) | ok |
| Fim de sessão com a janela visível | ok | ok |

Também: `ferramentas/bandeja/teste_bandeja.py` (aviso só 1x por sessão, textos do status e da dica, menu,
clique/duplo clique), `ferramentas/automacao/teste_janela.py` do PR #1 (9/9), os 28 testes de
`teste_rotinas.py` (inclui reservas e o limite de 4 contas), calculadora, Pokédex e erros de rede: passaram.

Prints: `aviso_balao.png`, `menu_bandeja.png`, `voltou_da_bandeja.png`.

## Regressão

- Hashes SHA-256 iguais antes e depois em 26 arquivos: `workers/`, `game/`, `rmt/`, `hunts/`,
  `browser/cdp.py`, `browser/web_host.py`, `app/manager.py`, `app/config.py`, `app/config_edit.py`,
  `app/settings_ui.py`, `config.toml`.
- Nenhum botão nem atalho mudou. Log: uma linha nova só no fim de sessão/instalador
  ("o Windows pediu para fechar (fim de sessão ou instalador): saindo pelo Sair").
- Menu: "Sair e parar as contas" virou "Sair" (texto pedido); F1 explica a bandeja.

## Build

`--distpath dist_novo`, ZIP de 133 MB, descompactado numa pasta nova, rodado sem Python no PATH: o
`instalador/fumaca.ps1` novo passou ("o X deixou o PokeNexus na bandeja; fechando pelo fim de sessão… Fumaça
ok") e os 18 fluxos acima também.

## Falta (depende do usuário)

1. **Farm com conta real** (o jogo simulado não prova o farm do PokeIdle): uma conta, 20 min visível +
   20 min minimizada + 60 min na bandeja com um recarregamento e uma ida ao Centro; Mercado dessa conta
   desligado só durante o teste. Precisa de autorização.
2. **Instalador e atualização de ponta a ponta com o instalador de verdade:** as ferramentas instalam em
   `%LOCALAPPDATA%\Programs\PokeNexus`, por cima do PokeNexus instalado do usuário. O mecanismo (Restart
   Manager) foi provado direto pela API do Windows com o `.exe`; o atualizador agora chama o mesmo `sair()`
   testado nos fluxos. Precisa de autorização para instalar por cima.
3. Commit e push (publica a atualização para todos).
