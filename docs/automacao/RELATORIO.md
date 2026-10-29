# Inicialização automática e bandeja

Entrega de 28/10/2026. O limite simultâneo de quatro contas foi mantido.

## Comportamento

Novos dados começam com início automático ligado. Na primeira execução desta versão, instalações
anteriores também recebem essa opção ligada; depois disso a escolha feita em Ajustes é preservada.
As contas ativas abrem com um intervalo configurável
(padrão: 3 s) e usam seu perfil persistente. Com sessão válida, o farm usa a hunt fixa ou a última
hunt registrada; no Centro também pode recuperar a hunt informada pelo servidor. Login inicial,
CAPTCHA, sessão expirada, termos novos, personagem novo e hunt ainda não escolhida exigem intervenção.
Não cria personagens nem escolhe uma área arbitrária. O PC precisa permanecer acordado e conectado.

O X e minimizar mantêm o programa na bandeja por padrão. O menu permite restaurar ou sair e parar
as contas. As opções podem ser desligadas; sem suporte à bandeja, fechar encerra normalmente.
A atualização do programa usa o encerramento explícito, para não ficar escondida esperando instalar.

Em segundo plano: interface a cada 5 s, sem repintar tabelas/log, sprites pausadas, fila de mensagens
em memória limitada. O log em disco continua completo. O farm agora respeita o intervalo de leitura
do DOM mesmo com mensagens frequentes do servidor. Os sockets continuam ativos.

A economia usa os botões nativos `#hunt-eco` e `#eco-sair`, conferidos no cliente público do jogo
1.375.3. A preferência anterior fica marcada no próprio perfil, sem ler credenciais. Ao voltar, ela
é restaurada, inclusive depois de recarregar. Preferência já ligada é preservada. Se os controles
mudarem no jogo, a tentativa de economia não impede a rotina de farm.

O gerenciador reserva vagas antes de abrir login/iniciar/reiniciar e serializa os comandos de uma
mesma conta. Parar tudo fecha também páginas de login e cancela partidas agendadas. Os demais
perfis não são interrompidos por uma falha individual.

Contas sem hunt fixa podem avançar automaticamente com o mesmo cálculo do Hunt Analyzer. O objetivo
pode ser XP do Pokémon, XP do treinador ou Ouro. O padrão reavalia a cada 15 minutos, exige ganho de
5% e aceita no máximo risco médio. Ritmos reais medidos por 10+ minutos corrigem a estimativa dentro
de uma faixa conservadora. A rotina não troca durante batalha, em modo manual/pausado nem quando há
hunt fixa.

## Verificação

- 28 testes de configuração, início/parada, reservas de conexão, retomada, recomendação de hunt e
  diagnóstico: passaram.
- Janela real Qt/WebEngine com quatro perfis temporários e servidor HTTP/WebSocket em localhost:
  início automático, entrada na hunt, batalhas durante a bandeja, economia, restauração após reload,
  minimizar, parar todas, fechar login reserva e encerrar páginas/thread: passaram.
- Testes existentes de tradução de rede, Pokédex e calculadora: passaram. O teste da Pokédex foi
  executado com `PYTHONIOENCODING=utf-8`, necessário para os símbolos impressos no terminal Windows.
- Build PyInstaller e teste de abertura do executável: passaram, incluindo o runtime MSVC exigido
  pelo Qt/WebEngine. O teste local não comprova ganho percentual de CPU/RAM nem execução com contas autenticadas no
  servidor real. Não foram usados perfis reais, credenciais ou compras.

Reproduzir no ambiente Python do projeto:

```powershell
python -m unittest discover -s ferramentas/automacao -p teste_rotinas.py -v
python ferramentas/automacao/teste_janela.py --saida <pasta-temporaria>
```

Os testes usam dados temporários. Nenhum serviço externo é necessário para o teste de janela e
nenhuma conta real foi aberta ou interrompida.

## Próxima etapa adiada

Os [termos atuais](https://pokeidle.io/terms) e o cliente público indicam limite por pessoa,
IP/rede e identificador do navegador. Redes compartilhadas podem solicitar liberação ao suporte,
que não amplia o limite por pessoa. Não basta alterar um número local ou trocar IP. Não foi
implementada expansão acima de quatro nem uma mudança de roteamento nesta entrega.

Outras melhorias possíveis: medir CPU/RAM com sessões reais autorizadas e separar os painéis
restantes de `app/gui.py` em módulos menores. Não fazem parte deste pacote.
